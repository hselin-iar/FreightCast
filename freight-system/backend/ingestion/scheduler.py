"""
backend/ingestion/scheduler.py — APScheduler entrypoint for batch ingestion & model retraining.

Cadence:
  - Daily:   BDI, Bunker prices (VLSFO/MGO), Market macro features (Brent, WTI, Iron Ore)
  - Weekly:  train_and_evaluate() on RETRAIN_SCHEDULE_CRON (default: Sunday midnight UTC)
  - Hourly:  AIS anchorage congestion rollup

Supports:
  - python3 -m backend.ingestion.scheduler --run-once
  - python3 -m backend.ingestion.scheduler --daemon
  - python3 -m backend.ingestion.scheduler --job [market|retrain|all]

DOC3 §FEATURE: Data Ingestion Layer & §4 Deployment.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config.constants import RETRAIN_SCHEDULE_CRON
from backend.engine import forecasting
from backend.ingestion.batch import (
    bdi_ingest,
    bunker_ingest,
    market_history_ingest,
)
from backend.warehouse import repository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [scheduler] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")


def run_market_ingestion() -> Dict[str, Any]:
    """Execute all daily market ingestion pipelines and write clean rows to warehouse."""
    logger.info("=== Starting Daily Market Ingestion ===")
    results = {}

    # 1. BDI Ingest
    try:
        bdi_res = bdi_ingest.run()
        results["bdi"] = {
            "rows_ingested": bdi_res.rows_ingested,
            "rows_rejected": bdi_res.rows_rejected,
            "alerts": bdi_res.alerts,
        }
        logger.info("BDI Ingest: %d ingested, %d rejected", bdi_res.rows_ingested, bdi_res.rows_rejected)
    except Exception as exc:
        logger.exception("BDI ingest failed: %s", exc)
        results["bdi"] = {"error": str(exc)}

    # 2. Bunker Ingest (VLSFO / MGO)
    try:
        bunker_res = bunker_ingest.run()
        results["bunker"] = {
            "rows_ingested": bunker_res.rows_ingested,
            "rows_rejected": bunker_res.rows_rejected,
            "alerts": bunker_res.alerts,
        }
        logger.info("Bunker Ingest: %d ingested, %d rejected", bunker_res.rows_ingested, bunker_res.rows_rejected)
    except Exception as exc:
        logger.exception("Bunker ingest failed: %s", exc)
        results["bunker"] = {"error": str(exc)}

    # 3. Macro Market History (Brent, WTI, Iron Ore)
    try:
        macro_res = market_history_ingest.run()
        rows = market_history_ingest.get_rows()
        if rows:
            repository.upsert_exogenous_features(rows)
        results["macro"] = {
            "rows_ingested": len(rows),
            "rows_rejected": macro_res.rows_rejected,
            "alerts": macro_res.alerts,
        }
        logger.info("Macro Ingest: %d rows upserted to ExogenousFeature", len(rows))
    except Exception as exc:
        logger.exception("Macro ingest failed: %s", exc)
        results["macro"] = {"error": str(exc)}

    logger.info("=== Market Ingestion Finished ===")
    return results


def run_model_retrain() -> Dict[str, Any]:
    """Execute scheduled walk-forward model retraining across all scope pairs."""
    logger.info("=== Starting Weekly Model Retraining Ladder ===")
    start_time = time.time()
    try:
        repository.invalidate_scope_cache()
        forecasting.train_and_evaluate()
        elapsed = round(time.time() - start_time, 2)
        logger.info("=== Model Retraining Complete in %.1fs ===", elapsed)
        return {"status": "success", "elapsed_seconds": elapsed}
    except Exception as exc:
        logger.exception("Model retraining failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def run_all_jobs() -> Dict[str, Any]:
    """Run market ingestion followed by model retraining."""
    ingest_summary = run_market_ingestion()
    retrain_summary = run_model_retrain()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ingestion": ingest_summary,
        "retraining": retrain_summary,
    }


def start_scheduler_daemon() -> None:
    """Start blocking APScheduler loop executing jobs on cron cadence."""
    scheduler = BlockingScheduler(timezone="UTC")

    # Daily market ingestion at 02:00 UTC
    scheduler.add_job(
        run_market_ingestion,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_market_ingest",
        name="Daily Market Data Ingestion (BDI, Bunker, Crude, Iron Ore)",
        replace_existing=True,
    )

    # Weekly retraining from constants.py (default: Sunday midnight UTC)
    # Parse RETRAIN_SCHEDULE_CRON (e.g. "0 0 * * 0")
    try:
        fields = RETRAIN_SCHEDULE_CRON.strip().split()
        if len(fields) == 5:
            m, h, dom, mon, dow = fields
            cron_trigger = CronTrigger(minute=m, hour=h, day=dom, month=mon, day_of_week=dow)
        else:
            cron_trigger = CronTrigger(day_of_week="sun", hour=0, minute=0)
    except Exception:
        cron_trigger = CronTrigger(day_of_week="sun", hour=0, minute=0)

    scheduler.add_job(
        run_model_retrain,
        trigger=cron_trigger,
        id="weekly_model_retrain",
        name=f"Weekly Forecasting Model Retrain ({RETRAIN_SCHEDULE_CRON})",
        replace_existing=True,
    )

    logger.info("APScheduler initialized:")
    logger.info("  - Job 1: Daily Market Ingest (02:00 UTC)")
    logger.info("  - Job 2: Weekly Retrain (%s UTC)", RETRAIN_SCHEDULE_CRON)
    logger.info("Scheduler daemon running... Press Ctrl+C to exit.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler daemon stopped.")


def main():
    parser = argparse.ArgumentParser(description="FreightCast Autonomous Ingestion & Retraining Scheduler")
    parser.add_argument("--run-once", action="store_true", help="Execute all scheduled jobs once immediately and exit")
    parser.add_argument("--daemon", action="store_true", help="Start long-running APScheduler background daemon")
    parser.add_argument("--job", choices=["market", "retrain", "all"], default="all", help="Specify single job to run with --run-once")

    args = parser.parse_args()

    if args.daemon:
        start_scheduler_daemon()
    elif args.run_once:
        if args.job == "market":
            run_market_ingestion()
        elif args.job == "retrain":
            run_model_retrain()
        else:
            run_all_jobs()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

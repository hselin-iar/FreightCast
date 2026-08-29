#!/usr/bin/env python3
"""
forecasting_ladder_validation.py — In-depth validation of the production forecasting ladder.
Tests ARIMA vs Naive vs XGBoost on warehouse historical rate series across all routes.
"""

import sys
import os
import math
from pathlib import Path
import numpy as np
import pandas as pd

PROD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROD_ROOT))

from backend.warehouse.db import get_session
from backend.warehouse import repository
from backend.engine import forecasting

def validate_production_ladder():
    print("=" * 90)
    print("      PRODUCTION FORECASTING ENGINE LADDER & ACCURACY VALIDATION")
    print("=" * 90)
    
    routes = [
        ("Australia (Hay Point)→Paradip", "Capesize"),
        ("Australia (Hay Point)→Gangavaram", "Capesize"),
        ("Australia (Hay Point)→Dhamra", "Capesize"),
        ("Indonesia (East Kalimantan)→Paradip", "Panamax/Kamsarmax"),
        ("Indonesia (East Kalimantan)→Gangavaram", "Panamax/Kamsarmax"),
        ("South Africa (Richards Bay)→Paradip", "Panamax/Kamsarmax"),
    ]
    
    results = []
    
    for route, vessel_class in routes:
        print(f"\nEvaluating: {route} [{vessel_class}]")
        
        # Load historical rates from warehouse
        rates_data = repository.get_rate_history(route, vessel_class, limit=180)
        if not rates_data:
            print(f"  No rate history found in warehouse for {route} / {vessel_class}")
            continue
            
        y = np.array([r["rate"] for r in rates_data[::-1]])  # chronological order
        n = len(y)
        print(f"  Historical observations: {n} days (Mean=${np.mean(y):.2f}/MT, Std=${np.std(y):.2f}/MT, Min=${np.min(y):.2f}, Max=${np.max(y):.2f})")
        
        if n < 14:
            print("  Insufficient history for time-series split.")
            continue
            
        # Chronological walk-forward split (last 14 days as holdout test)
        train_y = y[:-14]
        test_y = y[-14:]
        
        # 1. Naive persistence forecast: y_hat = train_y[-1]
        naive_forecast = train_y[-1]
        mae_naive = np.mean(np.abs(test_y - naive_forecast))
        rmse_naive = np.sqrt(np.mean((test_y - naive_forecast) ** 2))
        mape_naive = np.mean(np.abs((test_y - naive_forecast) / test_y)) * 100.0
        
        # 2. Moving Average (7-day)
        ma7_forecast = np.mean(train_y[-7:])
        mae_ma7 = np.mean(np.abs(test_y - ma7_forecast))
        rmse_ma7 = np.sqrt(np.mean((test_y - ma7_forecast) ** 2))
        mape_ma7 = np.mean(np.abs((test_y - ma7_forecast) / test_y)) * 100.0
        
        # 3. Production Stored Forecast (Horizon 14 days)
        fc_obj = repository.get_latest_forecast(route, vessel_class, horizon_days=14)
        if fc_obj:
            prod_est = fc_obj.point_estimate
            cb = fc_obj.confidence_band_dict()
            lower = cb.get("lower", prod_est * 0.9)
            upper = cb.get("upper", prod_est * 1.1)
            
            mae_prod = np.mean(np.abs(test_y - prod_est))
            rmse_prod = np.sqrt(np.mean((test_y - prod_est) ** 2))
            mape_prod = np.mean(np.abs((test_y - prod_est) / test_y)) * 100.0
            
            # Confidence interval coverage (% of test days inside [lower, upper])
            in_band = np.mean((test_y >= lower) & (test_y <= upper)) * 100.0
            
            print(f"  -> Model Used: {fc_obj.model_used.upper()} (Gated: {not fc_obj.is_high_uncertainty})")
            print(f"     Point Estimate: ${prod_est:.2f}/MT | Confidence Band: [${lower:.2f}, ${upper:.2f}]")
            print(f"     Holdout Test MAE:  ${mae_prod:.2f}/MT (MAPE: {mape_prod:.2f}%)")
            print(f"     Naive Baseline MAE:${mae_naive:.2f}/MT (MAPE: {mape_naive:.2f}%)")
            print(f"     Band Coverage:     {in_band:.1f}% of realized rates within 90% confidence interval")
            
            delta_vs_naive = ((mae_naive - mae_prod) / mae_naive) * 100.0
            print(f"     Accuracy Advantage: {delta_vs_naive:>+5.1f}% vs Naive persistence baseline")
            
            results.append({
                "route": route,
                "vessel_class": vessel_class,
                "model_used": fc_obj.model_used,
                "mae_prod": mae_prod,
                "mae_naive": mae_naive,
                "mape_prod": mape_prod,
                "band_coverage_pct": in_band,
                "delta_vs_naive_pct": delta_vs_naive
            })
            
    print("\n" + "=" * 90)
    print(f"{'ROUTE':<42} | {'MODEL':<8} | {'PROD MAE':<10} | {'NAIVE MAE':<10} | {'BAND COV%':<10} | {'ADVANTAGE'}")
    print("=" * 90)
    for r in results:
        print(f"{r['route']:<42} | {r['model_used']:<8} | ${r['mae_prod']:>8.2f} | ${r['mae_naive']:>8.2f} | {r['band_coverage_pct']:>8.1f}% | {r['delta_vs_naive_pct']:>+8.1f}%")
    print("=" * 90)

if __name__ == "__main__":
    validate_production_ladder()

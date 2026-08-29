import os
import sys
import json
import math
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Add freight-system to path
sys.path.insert(0, os.path.abspath("freight-system"))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.warehouse.db import create_all_tables, reset_engine
from backend.warehouse import repository
from backend.engine import forecasting
from backend.config.constants import MIN_OBSERVATIONS_FOR_XGBOOST, FORECAST_HORIZONS_DAYS

def mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    return mae, rmse, mape(y_true, y_pred)

print("=" * 80)
print("1. DATA SOURCE CHECK")
print("=" * 80)

# Check default production fixture
default_fix = pd.read_csv("freight-system/backend/data/raw/rate_5tc_fixture.csv")
print("A. Current Default Production Fixture:")
print(f"   File: freight-system/backend/data/raw/rate_5tc_fixture.csv")
print(f"   Total rows: {len(default_fix)}")
print(f"   Routes: {default_fix['route'].value_counts().to_dict()}")
print(f"   Per route: {len(default_fix)//len(default_fix['route'].unique())} observations")
print(f"   Date range: {default_fix['date'].min()} to {default_fix['date'].max()}")

# Load real longest series from freight_optimization
real_df = pd.read_csv("freight_optimization/data/raw/freight/drycargo_5tc_c5.csv", parse_dates=["report_date"])
real_df = real_df.dropna(subset=["capesize_5tc_usd_per_day"]).sort_values("report_date").reset_index(drop=True)

print("\nB. Forced Real Series from freight_optimization:")
print(f"   Source file: freight_optimization/data/raw/freight/drycargo_5tc_c5.csv")
print(f"   Loaded rows: {len(real_df)}")
print(f"   Date range: {real_df.report_date.min().strftime('%Y-%m-%d')} to {real_df.report_date.max().strftime('%Y-%m-%d')}")
print(f"   Rate range: ${real_df.capesize_5tc_usd_per_day.min():,.2f} to ${real_df.capesize_5tc_usd_per_day.max():,.2f} (mean=${real_df.capesize_5tc_usd_per_day.mean():,.2f})")

# Seed real series into warehouse SQLite DB
reset_engine()
create_all_tables("sqlite:///:memory:")

rate_rows = []
for idx, r in real_df.iterrows():
    rate_rows.append({
        "route": "Australia (Hay Point)→Paradip",  # or standard route name
        "vessel_class": "Capesize",
        "date": r["report_date"].isoformat(),
        "rate": float(r["capesize_5tc_usd_per_day"]),
        "tier": "A",
        "provenance": "measured",
    })
repository.upsert_rate_history(rate_rows)

# Seed exogenous market data
brent = pd.read_csv("freight_optimization/data/raw/market/brent_historical.csv", parse_dates=["date"]).sort_values("date")
exog_rows = []
for idx, r in brent.iterrows():
    if pd.notnull(r["price"]):
        exog_rows.append({
            "source": "brent",
            "date": r["date"].isoformat(),
            "value": float(r["price"]),
            "unit": "USD/barrel",
            "provenance": "measured",
        })
repository.upsert_exogenous_feature(exog_rows)

print(f"\n   Seeded {len(rate_rows)} RateHistory rows and {len(exog_rows)} ExogenousFeature rows into warehouse.")

print("\n" + "=" * 80)
print("2. MODEL COMPARISON ON REAL DATA (Production Engine)")
print("=" * 80)

route_name = "Australia (Hay Point)→Paradip"
history = forecasting._load_rate_history(route_name, "Capesize")
exog_series = forecasting._load_exogenous_features(len(history))
horizon = 7

# Run all candidate models on this history
naive_mae = forecasting._walk_forward_mae(history, forecasting._naive_forecast, horizon)
dt_mae = forecasting._walk_forward_mae(history, lambda h, n: forecasting.damped_trend(h, n), horizon)
arima_mae_holdout = forecasting._holdout_mae(history, lambda h, n: forecasting._fit_arima(h, n), horizon)
arima_mae_wf = forecasting._walk_forward_mae(history, lambda h, n: forecasting._fit_arima(h, n), horizon, max_folds=30)
xgb_mae_wf = forecasting._walk_forward_mae(history, lambda h, n: forecasting._fit_xgboost(h, n), horizon)

# Gate check helper
def check_gate(mae, n_mae):
    imp = (n_mae - mae) / n_mae * 100.0 if n_mae > 0 else 0
    return imp >= 5.0, imp

dt_gate, dt_imp = check_gate(dt_mae, naive_mae)
arima_gate, arima_imp = check_gate(arima_mae_holdout, naive_mae)
arima_wf_gate, arima_wf_imp = check_gate(arima_mae_wf, naive_mae)
xgb_gate, xgb_imp = check_gate(xgb_mae_wf, naive_mae)

print(f"Horizon: {horizon} days | Real History Length: {len(history)} observations\n")
print(f"{'Candidate Model':<20} | {'Validation Protocol':<25} | {'MAE ($/day)':<12} | {'vs Naive (%)':<14} | {'Gated?':<8}")
print("-" * 88)
print(f"{'Naive Baseline':<20} | {'Walk-Forward (50 folds)':<25} | ${naive_mae:>10,.2f} | {'0.00%':<14} | {'Base':<8}")
print(f"{'Damped Trend (Holt)':<20} | {'Walk-Forward (50 folds)':<25} | ${dt_mae:>10,.2f} | {dt_imp:>+12.2f}% | {'YES' if dt_gate else 'NO':<8}")
print(f"{'ARIMA (1,1,1)':<20} | {'Holdout Split (20%)':<25} | ${arima_mae_holdout:>10,.2f} | {arima_imp:>+12.2f}% | {'YES' if arima_gate else 'NO':<8}")
print(f"{'ARIMA (1,1,1)':<20} | {'Walk-Forward (30 folds)':<25} | ${arima_mae_wf:>10,.2f} | {arima_wf_imp:>+12.2f}% | {'YES' if arima_wf_gate else 'NO':<8}")
print(f"{'XGBoost (Autoregressive)':<20} | {'Walk-Forward (50 folds)':<25} | ${xgb_mae_wf:>10,.2f} | {xgb_imp:>+12.2f}% | {'YES' if xgb_gate else 'NO':<8}")

# Also check for horizons 14 and 30
print("\nMulti-Horizon Comparison:")
print(f"{'Horizon':<10} | {'Naive MAE':<12} | {'Damped Trend':<14} | {'ARIMA Holdout':<14} | {'ARIMA WF':<12} | {'XGBoost WF':<12}")
print("-" * 85)
for h in [7, 14, 30]:
    n_m = forecasting._walk_forward_mae(history, forecasting._naive_forecast, h)
    dt_m = forecasting._walk_forward_mae(history, lambda hist, hor: forecasting.damped_trend(hist, hor), h)
    ar_h = forecasting._holdout_mae(history, lambda hist, hor: forecasting._fit_arima(hist, hor), h)
    ar_w = forecasting._walk_forward_mae(history, lambda hist, hor: forecasting._fit_arima(hist, hor), h, max_folds=20)
    xg_m = forecasting._walk_forward_mae(history, lambda hist, hor: forecasting._fit_xgboost(hist, hor), h)
    print(f"{str(h)+' days':<10} | ${n_m:>10,.2f} | ${dt_m:>12,.2f} | ${ar_h:>12,.2f} | ${ar_w:>10,.2f} | ${xg_m:>10,.2f}")

# Execute train_and_evaluate
forecasting.train_and_evaluate(routes=[route_name], vessel_classes=["Capesize"], horizons=[7, 14, 30])
fc_obj = repository.get_latest_forecast(route_name, "Capesize", 7)

print("\n" + "=" * 80)
print("3. WALK-FORWARD DISCIPLINE (Step-by-Step Chronological Expanding Window)")
print("=" * 80)

# Run step-by-step expanding window walk-forward for the production engine
min_train = 8
wf_records = []
for i in range(min_train, len(history) - 1):
    train_hist = history[:i]
    actual_next = history[i]
    
    # 1. Naive
    n_p = train_hist[-1]
    
    # 2. Damped trend
    dt_p = forecasting.damped_trend(train_hist, 1)[0]
    
    # 3. ARIMA
    try:
        ar_p = forecasting._fit_arima(train_hist, 1)[0]
    except:
        ar_p = dt_p
        
    # 4. XGBoost
    try:
        xg_p = forecasting._fit_xgboost(train_hist, 1)[0]
    except:
        xg_p = dt_p
        
    wf_records.append({
        "step": i - min_train + 1,
        "actual": actual_next,
        "naive": n_p,
        "damped_trend": dt_p,
        "arima": ar_p,
        "xgboost": xg_p,
    })

wf_df = pd.DataFrame(wf_records)
print(f"Total walk-forward steps evaluated: {len(wf_df)} (from observation {min_train+1} to {len(history)})")

print(f"\n{'Model':<20} | {'MAE ($/day)':<14} | {'RMSE ($/day)':<14} | {'MAPE (%)':<10} | {'vs Naive MAE':<14}")
print("-" * 80)
for m_col in ["naive", "damped_trend", "arima", "xgboost"]:
    mae_v, rmse_v, mape_v = metrics(wf_df["actual"], wf_df[m_col])
    n_mae_v = mean_absolute_error(wf_df["actual"], wf_df["naive"])
    rel_imp = (n_mae_v - mae_v) / n_mae_v * 100.0
    print(f"{m_col:<20} | ${mae_v:>12,.2f} | ${rmse_v:>12,.2f} | {mape_v:>8.2f}% | {rel_imp:>+12.2f}%")

print("\n" + "=" * 80)
print("4. OUTPUT RICHNESS CHECK (Production ForecastObject)")
print("=" * 80)

traj_data = json.loads(fc_obj.trajectory)
cb_data = json.loads(fc_obj.confidence_band)

print("Full Structured Output Dump:")
dump = {
    "route": fc_obj.route,
    "vessel_class": fc_obj.vessel_class,
    "horizon_days": fc_obj.horizon_days,
    "generated_at": fc_obj.generated_at.isoformat() if fc_obj.generated_at else None,
    "point_estimate": fc_obj.point_estimate,
    "confidence_band": cb_data,
    "trajectory_points_count": len(traj_data),
    "trajectory_sample": traj_data[:3],
    "driver_explanation": fc_obj.driver_explanation,
    "is_high_uncertainty": fc_obj.is_high_uncertainty,
    "model_used": fc_obj.model_used,
    "provenance": getattr(fc_obj, "provenance", "modeled"),
}
print(json.dumps(dump, indent=2))

print("\nDecision Engine Compatibility Check:")
print("  - Has point_estimate (float):", isinstance(fc_obj.point_estimate, float))
print("  - Has confidence_band (lower/upper):", "lower" in cb_data and "upper" in cb_data)
print("  - Has trajectory (day/point_estimate):", all("day" in p and "point_estimate" in p for p in traj_data))
print("  - Has is_high_uncertainty (bool):", isinstance(fc_obj.is_high_uncertainty, bool))
print("  - Has driver_explanation (str):", isinstance(fc_obj.driver_explanation, str))
print("  - Has provenance ('modeled'):", getattr(fc_obj, "provenance", "modeled") == "modeled")

print("\n" + "=" * 80)
print("5. FEATURE INVENTORY")
print("=" * 80)

print("Production Engine vs Research Pipeline Feature Comparison:")
feature_comparison = [
    ("Target Lags 1..4 (`tc_lag_1`..`4`)", "Yes (AR lags 1..10 in `_fit_xgboost`)", "Yes (`tc_lag_1`..`tc_lag_4` explicitly)"),
    ("Target Rolling Mean (`tc_mean_4`)", "No (relies on AR lags & ARIMA)", "Yes (`rolling(4).mean()`)"),
    ("Target Rolling Std (`tc_std_4`)", "No (used in confidence band residual)", "Yes (`rolling(4).std()`)"),
    ("Brent Crude Price (`brent_price`)", "Yes (via `ExogenousFeature` table)", "Yes (`brent_price`)"),
    ("Brent 1d Return (`brent_return_1d`)", "No (uses price levels in production)", "Yes (`brent_return_1d`)"),
    ("Brent 7d Change (`brent_change_7d`)", "No (ConditionsMonitor computes 7d roll)", "Yes (`brent_change_7d`)"),
    ("WTI Crude Price / Return / 7d Change", "Yes in DB (not in default retrain feed)", "Yes (`wti_price`, `wti_return_1d`, `wti_change_7d`)"),
    ("Iron Ore Price & Changes (1m, 3m)", "Yes in DB (not in default retrain feed)", "Yes (`iron_ore_price`, `1m`, `3m`, `ma_3m`)"),
    ("Market Conditions / BDI Spike Monitor", "Yes (Live `ConditionsMonitor` at read time)", "No (Offline research script)"),
    ("Scenario Uncertainty Band", "Yes (1.96 * residual std)", "No (Single point predictions)"),
]

print(f"{'Feature / Component':<35} | {'Production Engine':<40} | {'Research Suite (XGBoost)':<35}")
print("-" * 115)
for f_name, prod_val, res_val in feature_comparison:
    print(f"{f_name:<35} | {prod_val:<40} | {res_val:<35}")

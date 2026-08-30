import sys
import os
import math
import random
sys.path.append(os.path.abspath("freight-system"))

from backend.engine.forecasting import _walk_forward_mae, _fit_xgboost_ar, damped_trend, _fit_arima

# Generate synthetic history (e.g. a sine wave with some noise)
random.seed(42)
history = [50000 + 20000 * math.sin(i / 10.0) + random.normalvariate(0, 1000) for i in range(200)]
horizon = 14

mae_naive = _walk_forward_mae(history, damped_trend, horizon, max_folds=3)
print(f"Naive MAE: {mae_naive:.2f}")

try:
    mae_arima = _walk_forward_mae(history, _fit_arima, horizon, max_folds=3)
    print(f"ARIMA MAE: {mae_arima:.2f}")
except Exception as e:
    print(f"ARIMA error: {e}")

try:
    mae_xgb = _walk_forward_mae(history, lambda h, hor: _fit_xgboost_ar(h, hor), horizon, max_folds=3)
    print(f"XGBoost AR MAE: {mae_xgb:.2f}")
except Exception as e:
    print(f"XGBoost error: {e}")

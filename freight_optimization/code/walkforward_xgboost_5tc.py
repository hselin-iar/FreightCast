import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
)

from xgboost import XGBRegressor


INPUT = "data/processed/final_5tc_ml_dataset.csv"
OUTPUT = "data/processed/5tc_walkforward_predictions.csv"


FEATURES = [
    "tc_lag_1",
    "tc_lag_2",
    "tc_lag_3",
    "tc_lag_4",
    "tc_mean_4",
    "tc_std_4",

    "brent_price",
    "brent_return_1d",
    "brent_change_7d",

    "wti_price",
    "wti_return_1d",
    "wti_change_7d",

    "iron_ore_price",
    "iron_ore_change_1m",
    "iron_ore_change_3m",
    "iron_ore_ma_3m",
]

TARGET = "target_next_5tc"


def mape(y_true, y_pred):

    y_true = np.asarray(
        y_true,
        dtype=float
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float
    )

    mask = y_true != 0

    return (
        np.mean(
            np.abs(
                (y_true[mask] - y_pred[mask])
                / y_true[mask]
            )
        )
        * 100
    )


def metrics(y_true, y_pred):

    mae = mean_absolute_error(
        y_true,
        y_pred
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_true,
            y_pred
        )
    )

    return mae, rmse, mape(
        y_true,
        y_pred
    )


def main():

    print("=" * 90)
    print("             WALK-FORWARD XGBOOST — CAPESIZE 5TC")
    print("=" * 90)
    print()

    df = pd.read_csv(
        INPUT,
        parse_dates=[
            "date",
            "target_date"
        ]
    )

    df = (
        df
        .sort_values("date")
        .reset_index(drop=True)
    )

    print(
        "Total samples:",
        len(df)
    )

    print()

    # ---------------------------------------------------------
    # Start only after enough observations exist for the
    # lag features and a meaningful tiny training set.
    # ---------------------------------------------------------

    min_train = 8

    predictions = []

    for i in range(
        min_train,
        len(df)
    ):

        train = df.iloc[
            :i
        ].copy()

        test = df.iloc[
            i:i + 1
        ].copy()

        X_train = train[
            FEATURES
        ]

        y_train = train[
            TARGET
        ]

        X_test = test[
            FEATURES
        ]

        y_test = test[
            TARGET
        ]

        model = XGBRegressor(
            n_estimators=80,
            max_depth=2,
            learning_rate=0.05,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            eval_metric="mae",
            reg_alpha=0.1,
            reg_lambda=2.0,
            random_state=42,
        )

        model.fit(
            X_train,
            y_train
        )

        xgb_pred = float(
            model.predict(
                X_test
            )[0]
        )

        # -----------------------------------------------------
        # Naive baseline:
        # next week's rate = current rate
        # -----------------------------------------------------

        naive_pred = float(
            test[
                "tc_lag_1"
            ].iloc[0]
        )

        actual = float(
            y_test.iloc[0]
        )

        predictions.append({
            "date":
                test["date"].iloc[0],

            "target_date":
                test["target_date"].iloc[0],

            "actual":
                actual,

            "naive":
                naive_pred,

            "xgboost":
                xgb_pred,

            "naive_abs_error":
                abs(
                    actual -
                    naive_pred
                ),

            "xgb_abs_error":
                abs(
                    actual -
                    xgb_pred
                ),
        })

    result = pd.DataFrame(
        predictions
    )

    result.to_csv(
        OUTPUT,
        index=False
    )

    print()
    print("=" * 90)
    print("                    WALK-FORWARD RESULTS")
    print("=" * 90)
    print()

    print(
        result.to_string(
            index=False
        )
    )

    y_true = result["actual"]

    naive = result["naive"]

    xgb = result["xgboost"]

    naive_mae, naive_rmse, naive_mape = metrics(
        y_true,
        naive
    )

    xgb_mae, xgb_rmse, xgb_mape = metrics(
        y_true,
        xgb
    )

    print()
    print("=" * 90)
    print("                         COMPARISON")
    print("=" * 90)
    print()

    print(
        f"{'Metric':<12}"
        f"{'Naive':>18}"
        f"{'XGBoost':>18}"
    )

    print("-" * 50)

    print(
        f"{'MAE':<12}"
        f"${naive_mae:>16,.2f}"
        f"${xgb_mae:>16,.2f}"
    )

    print(
        f"{'RMSE':<12}"
        f"${naive_rmse:>16,.2f}"
        f"${xgb_rmse:>16,.2f}"
    )

    print(
        f"{'MAPE':<12}"
        f"{naive_mape:>16.2f}%"
        f"{xgb_mape:>16.2f}%"
    )

    print()

    if xgb_mae < naive_mae:
        improvement = (
            1 -
            xgb_mae / naive_mae
        ) * 100

        print(
            f"XGBoost MAE improvement: "
            f"{improvement:.2f}%"
        )
    else:
        degradation = (
            xgb_mae / naive_mae -
            1
        ) * 100

        print(
            f"XGBoost MAE degradation: "
            f"{degradation:.2f}%"
        )

    print()

    print(
        "Saved:",
        OUTPUT
    )

    print()
    print("=" * 90)
    print("                         DONE")
    print("=" * 90)


if __name__ == "__main__":
    main()


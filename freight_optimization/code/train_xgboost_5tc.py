import pandas as pd
import numpy as np

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from xgboost import XGBRegressor


INPUT = "data/processed/5tc_oil_features.csv"


def mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mask = y_true != 0

    return (
        np.mean(
            np.abs(
                (y_true[mask] - y_pred[mask])
                / y_true[mask]
            )
        ) * 100
    )


def evaluate(name, y_true, y_pred):

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

    r2 = r2_score(
        y_true,
        y_pred
    )

    print()
    print(name)
    print("-" * 60)
    print(f"MAE  : ${mae:,.2f}/day")
    print(f"RMSE : ${rmse:,.2f}/day")
    print(f"MAPE : {mape(y_true, y_pred):.2f}%")
    print(f"R²   : {r2:.4f}")


def main():

    print("=" * 80)
    print("              CAPESIZE 5TC — XGBOOST V1")
    print("=" * 80)
    print()

    df = pd.read_csv(
        INPUT,
        parse_dates=["date"]
    )

    df = (
        df
        .sort_values("date")
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Create lag features from the target.
    # shift(1) ensures we never use the current target itself.
    # ---------------------------------------------------------

    for lag in [1, 2, 3, 4]:

        df[f"tc_lag_{lag}"] = (
            df["target_5tc"].shift(lag)
        )

    df["tc_mean_4"] = (
        df["target_5tc"]
        .shift(1)
        .rolling(4)
        .mean()
    )

    df["tc_std_4"] = (
        df["target_5tc"]
        .shift(1)
        .rolling(4)
        .std()
    )

    # ---------------------------------------------------------
    # Target: next observed 5TC.
    #
    # Because the underlying target observations are sparse,
    # this is "next observed observation", not guaranteed 7 days.
    # ---------------------------------------------------------

    df["target_next"] = (
        df["target_5tc"].shift(-1)
    )

    # Remove rows without sufficient history.
    df = df.dropna(
        subset=[
            "tc_lag_1",
            "tc_lag_2",
            "tc_lag_3",
            "tc_lag_4",
            "tc_mean_4",
            "tc_std_4",
            "brent_price",
            "brent_change_7d",
            "wti_price",
            "wti_change_7d",
            "target_next",
        ]
    ).reset_index(drop=True)

    features = [
        "tc_lag_1",
        "tc_lag_2",
        "tc_lag_3",
        "tc_lag_4",
        "tc_mean_4",
        "tc_std_4",
        "brent_price",
        "brent_change_7d",
        "wti_price",
        "wti_change_7d",
    ]

    X = df[features]
    y = df["target_next"]

    # ---------------------------------------------------------
    # Chronological split
    # ---------------------------------------------------------

    split = int(
        len(df) * 0.70
    )

    X_train = X.iloc[:split]
    X_test = X.iloc[split:]

    y_train = y.iloc[:split]
    y_test = y.iloc[split:]

    print(
        "Total samples:",
        len(df)
    )

    print(
        "Train:",
        len(X_train)
    )

    print(
        "Test:",
        len(X_test)
    )

    print()

    print(
        "Train dates:",
        df["date"].iloc[:split].min(),
        "→",
        df["date"].iloc[:split].max()
    )

    print(
        "Test dates:",
        df["date"].iloc[split:].min(),
        "→",
        df["date"].iloc[-1]
    )

    # ---------------------------------------------------------
    # Naive persistence baseline
    # ---------------------------------------------------------

    naive_pred = X_test[
        "tc_lag_1"
    ].to_numpy()

    evaluate(
        "NAIVE PERSISTENCE",
        y_test,
        naive_pred
    )

    # ---------------------------------------------------------
    # Small XGBoost model
    # ---------------------------------------------------------

    model = XGBRegressor(
        n_estimators=100,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        eval_metric="mae",
        random_state=42,
    )

    model.fit(
        X_train,
        y_train
    )

    pred = model.predict(
        X_test
    )

    evaluate(
        "XGBOOST V1",
        y_test,
        pred
    )

    # ---------------------------------------------------------
    # Predictions
    # ---------------------------------------------------------

    results = pd.DataFrame({
        "date": df["date"].iloc[split:].values,
        "actual": y_test.values,
        "naive": naive_pred,
        "xgboost": pred,
    })

    results["naive_error"] = (
        results["actual"]
        - results["naive"]
    )

    results["xgb_error"] = (
        results["actual"]
        - results["xgboost"]
    )

    print()
    print("=" * 80)
    print("                    TEST PREDICTIONS")
    print("=" * 80)
    print()

    print(
        results.to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Feature importance
    # ---------------------------------------------------------

    importance = pd.DataFrame({
        "feature": features,
        "importance": model.feature_importances_,
    })

    importance = importance.sort_values(
        "importance",
        ascending=False
    )

    print()
    print("=" * 80)
    print("                   FEATURE IMPORTANCE")
    print("=" * 80)
    print()

    print(
        importance.to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Save model
    # ---------------------------------------------------------

    model.save_model(
        "models/xgboost_5tc_v1.json"
    )

    results.to_csv(
        "data/processed/5tc_xgboost_v1_predictions.csv",
        index=False
    )

    print()
    print(
        "Model saved:",
        "models/xgboost_5tc_v1.json"
    )

    print(
        "Predictions saved:",
        "data/processed/5tc_xgboost_v1_predictions.csv"
    )

    print()
    print("=" * 80)
    print("                         DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()

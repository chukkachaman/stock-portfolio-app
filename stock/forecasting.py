import numpy as np
import pandas as pd
import yfinance as yf
from xgboost import XGBRegressor

LAG_DAYS = 5
FORECAST_DAYS = 7


def _build_lag_features(prices):
    """Turn a 1-D price series into (X, y) rows of LAG_DAYS trailing closes -> next close."""
    rows = []
    targets = []
    for i in range(LAG_DAYS, len(prices)):
        rows.append(prices[i - LAG_DAYS:i])
        targets.append(prices[i])
    return np.array(rows), np.array(targets)


def generate_forecast(symbol, forecast_days=FORECAST_DAYS):
    """Fetch ~1y of daily history for `symbol` and forecast the next `forecast_days`
    closing prices with a gradient-boosted regressor trained on trailing-window lags.

    Returns a dict with historical (date, price) pairs and forecast (date, price) pairs,
    or an 'error' key if there isn't enough history to train on.
    """
    history = yf.Ticker(symbol).history(period="1y", interval="1d")

    if history.empty or len(history) < LAG_DAYS + 10:
        return {"error": f"Not enough historical data for {symbol}."}

    closes = history["Close"].to_numpy()
    dates = history.index

    X, y = _build_lag_features(closes)

    model = XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05)
    model.fit(X, y)

    window = list(closes[-LAG_DAYS:])
    last_date = dates[-1]
    forecast = []

    for _ in range(forecast_days):
        next_price = float(model.predict(np.array([window]))[0])
        last_date = last_date + pd.Timedelta(days=1)
        forecast.append({"date": last_date.strftime("%Y-%m-%d"), "price": round(next_price, 2)})
        window = window[1:] + [next_price]

    historical = [
        {"date": d.strftime("%Y-%m-%d"), "price": round(float(p), 2)}
        for d, p in zip(dates[-60:], closes[-60:])
    ]

    return {
        "symbol": symbol,
        "historical": historical,
        "forecast": forecast,
    }

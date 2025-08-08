import pandas as pd
import numpy as np
from typing import List, Dict
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import joblib
import torch

# Загрузка обученных моделей
scaler = joblib.load("model/scaler.pkl")
model = joblib.load("model/signal_model.pkl")

def generate_signal(symbol: str, ohlcv: List[List]) -> Dict:
    try:
        # Преобразование входных данных в DataFrame
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.astype(float)

        # Расчёт технических индикаторов
        df["ema_50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
        df["ema_200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()

        macd = MACD(close=df["close"], window_fast=12, window_slow=26, window_sign=9)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()

        df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()
        df["atr"] = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range()
        df["vol_avg"] = df["volume"].rolling(window=20).mean()

        latest = df.iloc[-1]

        # Подготовка признаков для модели
        features = np.array([
            latest["close"],
            latest["ema_50"],
            latest["ema_200"],
            latest["macd"],
            latest["macd_signal"],
            latest["rsi"],
            latest["volume"] / (latest["vol_avg"] + 1e-9)
        ]).reshape(1, -1)

        # Прогон через scaler и модель
        X_scaled = scaler.transform(features)
        with torch.no_grad():
            X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
            prediction = model(X_tensor)
            prob = float(prediction.squeeze().item())

        # Фильтр по уверенности
        if prob < 0.8:
            return {"symbol": symbol, "position": "NONE"}

        # Определение направления позиции
        position = "LONG" if latest["ema_50"] > latest["ema_200"] and latest["macd"] > latest["macd_signal"] else "SHORT"

        entry = latest["close"]
        atr = latest["atr"]
        tp = entry + 2 * atr if position == "LONG" else entry - 2 * atr
        sl = entry - 1 * atr if position == "LONG" else entry + 1 * atr

        return {
            "symbol": symbol,
            "position": position,
            "entry": round(entry, 4),
            "tp": round(tp, 4),
            "sl": round(sl, 4),
            "confidence": round(prob * 100, 2)
        }

    except Exception as e:
        return {"symbol": symbol, "position": "NONE", "error": str(e)}

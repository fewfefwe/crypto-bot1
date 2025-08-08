import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from core.bybit_api import BybitAPI

SAVE_PATH = "./data/market_data.csv"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "AVAXUSDT"]
INTERVAL = "15"
LIMIT = 300  # кол-во свечей на одну монету

api = BybitAPI()

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()
    df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    return df

def process_symbol(symbol: str) -> pd.DataFrame:
    ohlcv = api.get_ohlcv(symbol, interval=INTERVAL, limit=LIMIT)
    if not ohlcv or len(ohlcv) < 50:
        print(f"⚠️ Недостаточно данных для {symbol}")
        return pd.DataFrame()

    df = pd.DataFrame([row[:6] for row in ohlcv], columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.astype(float)
    df["symbol"] = symbol
    df = compute_indicators(df)
    df.dropna(inplace=True)
    return df

def main():
    all_data = []

    for symbol in SYMBOLS:
        print(f"📥 Загрузка {symbol}...")
        df = process_symbol(symbol)
        if not df.empty:
            all_data.append(df)

    if all_data:
        result = pd.concat(all_data)
        os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
        result.to_csv(SAVE_PATH, index=False)
        print(f"✅ Данные сохранены в: {SAVE_PATH}")
    else:
        print("❌ Не удалось собрать данные.")

if __name__ == "__main__":
    main()

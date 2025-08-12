import csv
import os
from datetime import datetime
from typing import Dict, Any

SIGNALS_FILE = "signals_log.csv"   # у тебя уже есть — сохраним формат
TRADES_FILE  = "trades_log.csv"    # новая таблица исходов

FIELDS_SIGNALS = [
    "signal_id","ts","symbol","position","entry","sl","tp",
    "score","confidence","rr_ratio","timeframe","extras"
]
FIELDS_TRADES = [
    "signal_id","symbol","opened_at","closed_at","close_price",
    "result","pnl_pct","rr_real","notes"
]

def _ensure(path: str, fields):
    new = not os.path.exists(path)
    f = open(path, "a", newline="", encoding="utf-8")
    if new:
        csv.DictWriter(f, fieldnames=fields).writeheader()
    return f

def log_signal_row(row: Dict[str, Any]):
    f = _ensure(SIGNALS_FILE, FIELDS_SIGNALS)
    with f:
        csv.DictWriter(f, fieldnames=FIELDS_SIGNALS).writerow(row)

def log_trade_row(row: Dict[str, Any]):
    f = _ensure(TRADES_FILE, FIELDS_TRADES)
    with f:
        csv.DictWriter(f, fieldnames=FIELDS_TRADES).writerow(row)

def make_signal_id(symbol: str) -> str:
    return f"{symbol}:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

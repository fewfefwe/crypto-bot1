import json
import os
from datetime import datetime

OPEN_TRADES_FILE = "open_trades.json"
CLOSED_TRADES_FILE = "signals_log.csv"


def load_open_trades():
    """Загружаем активные сделки"""
    if not os.path.exists(OPEN_TRADES_FILE):
        return []

    try:
        with open(OPEN_TRADES_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except json.JSONDecodeError:
        # Если файл повреждён, очищаем
        return []


def save_open_trades(trades):
    """Сохраняем активные сделки"""
    with open(OPEN_TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


def add_open_trade(signal: dict):
    """Добавляем новую сделку в отслеживание"""
    trades = load_open_trades()
    trade = {
        "symbol": signal["symbol"],
        "position": signal["position"],
        "entry": signal["entry"],
        "tp": signal["tp"],
        "sl": signal["sl"],
        "risk": signal.get("risk", 0),
        "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    trades.append(trade)
    save_open_trades(trades)


def close_trade(symbol: str, result_percent: float):
    """Закрываем сделку и сохраняем результат в лог"""
    trades = load_open_trades()
    new_trades = [t for t in trades if t["symbol"] != symbol]
    save_open_trades(new_trades)

    # Запись в CSV
    header_needed = not os.path.exists(CLOSED_TRADES_FILE)
    with open(CLOSED_TRADES_FILE, "a", encoding="utf-8") as f:
        if header_needed:
            f.write("datetime,symbol,position,entry,tp,sl,risk,profit_%\n")
        for t in trades:
            if t["symbol"] == symbol:
                f.write(f"{t['opened_at']},{t['symbol']},{t['position']},{t['entry']},{t['tp']},{t['sl']},{t['risk']},{result_percent}\n")


def check_open_trades(get_price_func):
    """
    Проверяем открытые сделки на достижение TP или SL.
    get_price_func(symbol) -> float
    """
    trades = load_open_trades()
    if not trades:
        return

    updated_trades = []

    for trade in trades:
        current_price = get_price_func(trade["symbol"])
        if current_price == 0:
            updated_trades.append(trade)
            continue

        # Проверяем условия закрытия
        if trade["position"] == "LONG":
            if current_price >= trade["tp"]:
                close_trade(trade["symbol"], 100)
                print(f"✅ TP достигнут по {trade['symbol']}")
                continue
            elif current_price <= trade["sl"]:
                close_trade(trade["symbol"], -50)
                print(f"❌ SL сработал по {trade['symbol']}")
                continue

        if trade["position"] == "SHORT":
            if current_price <= trade["tp"]:
                close_trade(trade["symbol"], 100)
                print(f"✅ TP достигнут по {trade['symbol']}")
                continue
            elif current_price >= trade["sl"]:
                close_trade(trade["symbol"], -50)
                print(f"❌ SL сработал по {trade['symbol']}")
                continue

        # Если сделка ещё активна
        updated_trades.append(trade)

    save_open_trades(updated_trades)

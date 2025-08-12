# utils/trade_tracker.py
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

OPEN_TRADES_FILE = "open_trades.json"
TRADES_LOG_FILE  = "trades_log.csv"


# ---------- low-level io ----------

def _read_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            if not txt:
                return None
            return json.loads(txt)
    except Exception:
        return None

def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- open trades store ----------

def load_open_trades() -> List[Dict]:
    """Возвращает список открытых сделок. Гарантирует список."""
    data = _read_json(OPEN_TRADES_FILE)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # на всякий случай поддержим старый формат, но лучше очистить файл
        return list(data.values())
    return []

def save_open_trades(trades: List[Dict]) -> None:
    _write_json(OPEN_TRADES_FILE, trades)


# ---------- helpers ----------

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _ensure_signal_id(signal: Dict) -> str:
    sid = signal.get("signal_id")
    if sid and isinstance(sid, str):
        return sid
    # Fallback: если вдруг забыли присвоить — сконструируем
    sid = f"{signal.get('symbol','UNKNOWN')}|{int(datetime.now().timestamp())}"
    signal["signal_id"] = sid
    return sid


# ---------- public api ----------

def add_open_trade(signal: Dict) -> None:
    """
    Добавляет сделку в список открытых.
    Требует уникальный signal_id (мы его проставляем в bot.py).
    Если по этому signal_id уже существует — заменяем (защита от дублей).
    """
    trades = load_open_trades()
    sid = _ensure_signal_id(signal)

    # Собираем компактную запись
    item = {
        "signal_id": sid,
        "symbol": signal["symbol"],
        "position": signal["position"],            # LONG/SHORT
        "entry": float(signal["entry"]),
        "tp": float(signal["tp"]),
        "sl": float(signal["sl"]),
        "risk_pct": float(signal.get("risk_pct", 1.0)),
        "leverage": int(signal.get("leverage", 5)),
        "rr_ratio": float(signal.get("rr_ratio", 0)),
        "opened_at": _now_str(),
    }

    # Уберём любой старый элемент с тем же signal_id
    trades = [t for t in trades if t.get("signal_id") != sid]
    trades.append(item)
    save_open_trades(trades)

def get_open_trade(signal_id: str) -> Optional[Dict]:
    for t in load_open_trades():
        if t.get("signal_id") == signal_id:
            return t
    return None

def remove_open_trade(signal_id: str) -> None:
    trades = load_open_trades()
    trades = [t for t in trades if t.get("signal_id") != signal_id]
    save_open_trades(trades)


def _append_trade_log(row: Dict) -> None:
    """Пишем факт закрытия в trades_log.csv (с заголовком при первом запуске)."""
    header_needed = not os.path.exists(TRADES_LOG_FILE)
    with open(TRADES_LOG_FILE, "a", encoding="utf-8") as f:
        if header_needed:
            f.write(
                "signal_id,symbol,position,entry,tp,sl,risk_pct,leverage,rr_ratio,opened_at,"
                "closed_at,status,closed_price,pnl_pct\n"
            )
        f.write(
            f"{row['signal_id']},{row['symbol']},{row['position']},{row['entry']},{row['tp']},{row['sl']},"
            f"{row['risk_pct']},{row['leverage']},{row['rr_ratio']},{row['opened_at']},"
            f"{row['closed_at']},{row['status']},{row['closed_price']},{row['pnl_pct']}\n"
        )


def _pnl_percent(position: str, entry: float, price: float) -> float:
    """
    PnL в процентах по цене (без учёта плеча — для честной статистики модели).
    LONG:  (price/entry - 1) * 100
    SHORT: (entry/price - 1) * 100
    """
    if position == "LONG":
        return (price / entry - 1.0) * 100.0
    else:
        return (entry / price - 1.0) * 100.0


def close_trade(signal_id, status, closed_price) -> Optional[Dict]:
    """
    Закрывает сделку по signal_id.
    status: 'TP' | 'SL' | 'MANUAL'
    Возвращает строку-лог (dict) или None, если не нашли сделку.
    """
    trade = get_open_trade(signal_id)
    if not trade:
        return None

    remove_open_trade(signal_id)

    pnl_pct = round(_pnl_percent(trade["position"], trade["entry"], float(closed_price)), 4)

    row = {
        "signal_id": signal_id,
        "symbol": trade["symbol"],
        "position": trade["position"],
        "entry": trade["entry"],
        "tp": trade["tp"],
        "sl": trade["sl"],
        "risk_pct": trade["risk_pct"],
        "leverage": trade["leverage"],
        "rr_ratio": trade["rr_ratio"],
        "opened_at": trade["opened_at"],
        "closed_at": _now_str(),
        "status": status,                  # TP/SL/MANUAL
        "closed_price": float(closed_price),
        "pnl_pct": pnl_pct,
    }
    _append_trade_log(row)
    return row


def check_open_trades(get_price_func) -> None:
    """
    Проверяем открытые сделки на TP/SL и закрываем по signal_id.
    get_price_func(symbol) -> float
    """
    trades = load_open_trades()
    if not trades:
        return

    still_open: List[Dict] = []
    for t in trades:
        try:
            symbol   = t["symbol"]
            side     = t["position"]
            entry    = float(t["entry"])
            tp       = float(t["tp"])
            sl       = float(t["sl"])
            sid      = t["signal_id"]

            price = float(get_price_func(symbol) or 0.0)
            if price <= 0:
                # если котировки нет — оставим открытую
                still_open.append(t)
                continue

            hit_tp = (price >= tp) if side == "LONG" else (price <= tp)
            hit_sl = (price <= sl) if side == "LONG" else (price >= sl)

            if hit_tp:
                row = close_trade(sid, status="TP", closed_price=price)
                print(f"✅ TP достигнут по {symbol} (signal_id={sid}, price={price})")
                continue
            if hit_sl:
                row = close_trade(sid, status="SL", closed_price=price)
                print(f"❌ SL сработал по {symbol} (signal_id={sid}, price={price})")
                continue

            # иначе оставляем открытую
            still_open.append(t)

        except Exception as e:
            # на всякий случай не теряем сделку при ошибке
            print(f"⚠️ check_open_trades error on {t}: {e}")
            still_open.append(t)

    save_open_trades(still_open)

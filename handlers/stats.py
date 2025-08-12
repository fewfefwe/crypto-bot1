# handlers/stats.py
import csv
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

router = Router()

TRADES_FILE  = "trades_log.csv"    # новый формат (из utils/trade_tracker.py)
SIGNALS_FILE = "signals_log.csv"   # старый формат (если вдруг есть)

# ---------- helpers ----------

def _parse_dt(val: str):
    """Пробуем ISO и '%Y-%m-%d %H:%M:%S'."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

# ---------- loaders ----------

def _load_from_trades(days: int):
    """trades_log.csv: считаем по closed_at и pnl_pct."""
    if not os.path.exists(TRADES_FILE):
        return None

    cutoff = datetime.now() - timedelta(days=days)
    rows = []
    with open(TRADES_FILE, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            dt = _parse_dt(row.get("closed_at"))
            if not dt or dt < cutoff:
                continue
            rows.append({
                "pnl_pct": _safe_float(row.get("pnl_pct")),
                "rr_ratio": _safe_float(row.get("rr_ratio")),
                "status": row.get("status", ""),
                "symbol": row.get("symbol", ""),
            })
    return rows

def _load_from_signals(days: int):
    """signals_log.csv: совместимость со старым форматом."""
    if not os.path.exists(SIGNALS_FILE):
        return None

    cutoff = datetime.now() - timedelta(days=days)
    rows = []
    with open(SIGNALS_FILE, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            dt = _parse_dt(row.get("closed_at")) or _parse_dt(row.get("datetime"))
            if not dt or dt < cutoff:
                continue
            # положит/отриц — по quality; RR — rr_ratio если есть
            rows.append({
                "quality": row.get("quality", ""),
                "rr_ratio": _safe_float(row.get("rr_ratio")),
                "symbol": row.get("symbol", ""),
            })
    return rows

# ---------- stats ----------

def calculate_stats(days: int) -> str:
    # 1) пробуем новый формат
    rows = _load_from_trades(days)
    if rows is not None:
        total = len(rows)
        if total == 0:
            return f"📊 За последние {days} дн. закрытых сделок нет."
        positive = sum(1 for r in rows if r["pnl_pct"] > 0)
        negative = sum(1 for r in rows if r["pnl_pct"] < 0)
        avg_rr   = sum(r["rr_ratio"] for r in rows) / total if total else 0.0
        win_rate = (positive / total) * 100 if total else 0.0
        return (
            f"📊 Статистика за {days} дн. (по закрытым сделкам)\n\n"
            f"Всего закрытых: {total}\n"
            f"✅ Положительных: {positive}\n"
            f"❌ Отрицательных: {negative}\n"
            f"📈 WinRate: {win_rate:.2f}%\n"
            f"⚖ Средний RR: {avg_rr:.2f}"
        )

    # 2) иначе пробуем старый формат
    rows = _load_from_signals(days)
    if rows is not None:
        total = len(rows)
        if total == 0:
            return f"📊 За последние {days} дн. сигналов не было."
        positive = sum(1 for r in rows if "✅" in r.get("quality", ""))
        negative = sum(1 for r in rows if "❌" in r.get("quality", ""))
        avg_rr   = sum(_safe_float(r.get("rr_ratio")) for r in rows) / total if total else 0.0
        win_rate = (positive / total) * 100 if total else 0.0
        return (
            f"📊 Статистика за {days} дн. (по сигналам)\n\n"
            f"Всего сигналов: {total}\n"
            f"✅ Положительных: {positive}\n"
            f"❌ Отрицательных: {negative}\n"
            f"📈 WinRate: {win_rate:.2f}%\n"
            f"⚖ Средний RR: {avg_rr:.2f}"
        )

    # 3) нет файлов вообще
    return "📊 Данных пока нет: не найдено ни trades_log.csv, ни signals_log.csv."

# ---------- UI ----------

def get_period_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 1 день",  callback_data="stats_1"),
            InlineKeyboardButton(text="📅 7 дней",  callback_data="stats_7"),
            InlineKeyboardButton(text="📅 30 дней", callback_data="stats_30"),
        ]
    ])

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    await message.answer("Выберите период для статистики:", reply_markup=get_period_keyboard())

@router.callback_query(F.data.startswith("stats_"))
async def callback_stats(callback: types.CallbackQuery):
    days = int(callback.data.split("_")[1])
    text = calculate_stats(days)
    await callback.message.edit_text(text, reply_markup=get_period_keyboard())
    await callback.answer()

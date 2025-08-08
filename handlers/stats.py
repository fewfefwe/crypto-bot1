import csv
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

LOG_FILE = "signals_log.csv"

def load_signals(period_days: int):
    """Загружает сигналы за последние N дней"""
    signals = []
    try:
        with open(LOG_FILE, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            cutoff_date = datetime.now() - timedelta(days=period_days)
            for row in reader:
                dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
                if dt >= cutoff_date:
                    signals.append(row)
    except FileNotFoundError:
        pass
    return signals

def calculate_stats(signals: list, days: int):
    """Вычисляет статистику по сигналам"""
    total = len(signals)
    if total == 0:
        return f"📊 За последние {days} дн. сигналов не было."

    positive = sum(1 for s in signals if "✅" in s["quality"])
    negative = sum(1 for s in signals if "❌" in s["quality"])
    avg_rr = sum(float(s["rr_ratio"] or 0) for s in signals) / total

    win_rate = (positive / total) * 100 if total else 0

    return (
        f"📊 Статистика за {days} дн.:\n\n"
        f"Всего сигналов: {total}\n"
        f"✅ Положительных: {positive}\n"
        f"❌ Отрицательных: {negative}\n"
        f"📈 WinRate: {win_rate:.2f}%\n"
        f"⚖ Средний RR: {avg_rr:.2f}"
    )

# --- Клавиатура выбора периода ---
def get_period_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 1 день", callback_data="stats_1"),
            InlineKeyboardButton(text="📅 7 дней", callback_data="stats_7"),
            InlineKeyboardButton(text="📅 30 дней", callback_data="stats_30"),
        ]
    ])

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Вызывает меню выбора периода"""
    await message.answer("Выберите период для статистики:", reply_markup=get_period_keyboard())

@router.callback_query(F.data.startswith("stats_"))
async def callback_stats(callback: types.CallbackQuery):
    """Обработка выбора периода"""
    days = int(callback.data.split("_")[1])
    signals = load_signals(days)
    stats_text = calculate_stats(signals, days)
    
    # Меняем текст текущего сообщения
    await callback.message.edit_text(stats_text, reply_markup=get_period_keyboard())
    await callback.answer()

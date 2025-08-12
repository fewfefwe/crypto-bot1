# handlers/signals.py  — версия с edit_text, «Назад» и «Обновить»

import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from core.bybit_api import BybitAPI
from core.filters import filter_by_volume, apply_all_filters
from core.signal_generator import generate_signal
from core.risk_manager import evaluate_risk
from utils.format_text import format_signal_text

router = Router()

# ---------- UI ----------
def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")]
    ])

def signals_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Обновить", callback_data="signals_rescan")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu")]
    ])

LOADING_TEXT = "⏳ Поиск актуальных сигналов, подождите..."

# ---------- Внутренняя логика поиска ----------
async def _scan_and_render(limit: int = 3) -> str:
    """
    Возвращает готовый текст для вывода:
    - сводка по количеству пар/фильтрам
    - до `limit` лучших сигналов в формате format_signal_text(...)
    """
    api = BybitAPI()

    # Получаем пары и фильтруем
    all_pairs = api.get_usdt_pairs()
    volume_filtered = filter_by_volume(all_pairs)
    final_pairs = apply_all_filters(volume_filtered, api.get_ohlcv)

    header = (
        "🔄 Запуск анализа рынка…\n"
        f"📊 Всего пар: {len(all_pairs)}\n"
        f"✅ После фильтра объёма: {len(volume_filtered)}\n"
        f"🧹 После всех фильтров: {len(final_pairs)}\n"
    )

    sent = 0
    chunks: list[str] = []
    for pair in final_pairs:
        # 15m или 60? — оставляю твоё 60 как было
        ohlcv = api.get_ohlcv(pair["symbol"], interval="60", limit=220)  # 220, чтобы хватало на EMA200
        if not ohlcv:
            continue

        signal = generate_signal(pair["symbol"], ohlcv)
        signal = evaluate_risk(signal)

        # Пропускаем плохие сигналы
        if isinstance(signal, dict) and signal.get("quality") and "❌" in signal["quality"]:
            continue

        # Формат
        try:
            text = format_signal_text(signal)
        except Exception:
            # На всякий случай, если где-то нет ожидаемых полей
            text = f"• {pair['symbol']}: {signal}"

        chunks.append(text)
        sent += 1
        if sent >= limit:
            break

    if sent == 0:
        return header + "\n😕 Подходящих сигналов не найдено."
    else:
        return header + "\n".join(chunks)

# ---------- Хэндлеры: кнопки (edit_text) ----------
@router.callback_query(F.data == "signals")
async def show_signals(callback: CallbackQuery):
    # Сначала показываем «грузится», чтобы пользователь видел реакцию
    await callback.message.edit_text(LOADING_TEXT, reply_markup=signals_menu_kb())
    await callback.answer()

    # Сканим и заменяем текст тем же сообщением
    text = await _scan_and_render(limit=3)
    await callback.message.edit_text(text, reply_markup=signals_menu_kb(), parse_mode="HTML")

@router.callback_query(F.data == "signals_rescan")
async def rescan_signals(callback: CallbackQuery):
    await callback.message.edit_text("🔁 Обновляю…", reply_markup=signals_menu_kb())
    await callback.answer()
    text = await _scan_and_render(limit=3)
    await callback.message.edit_text(text, reply_markup=signals_menu_kb(), parse_mode="HTML")

# ---------- Хэндлер команды /signal (оставляем для удобства) ----------
@router.message(Command("signal"))
async def send_signals(message: Message):
    # Отправим одно служебное и будем редактировать его
    msg = await message.answer(LOADING_TEXT)

    try:
        text = await _scan_and_render(limit=3)
        await msg.edit_text(text, reply_markup=signals_menu_kb(), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"⚠️ Ошибка при поиске сигналов:\n{e}", reply_markup=back_menu_kb())

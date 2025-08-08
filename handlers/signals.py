from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from core.bybit_api import BybitAPI
from core.filters import filter_by_volume, apply_all_filters
from core.signal_generator import generate_signal
from core.risk_manager import evaluate_risk
from utils.format_text import format_signal_text

router = Router()

@router.message(Command("signal"))
async def send_signals(message: Message):
    await message.answer("⏳ Поиск актуальных сигналов, подождите...")

    api = BybitAPI()
    try:
        # Получаем пары
        all_pairs = api.get_usdt_pairs()
        volume_filtered = filter_by_volume(all_pairs)
        final_pairs = apply_all_filters(volume_filtered, api.get_ohlcv)

        sent = 0
        for pair in final_pairs:
            ohlcv = api.get_ohlcv(pair["symbol"], interval="60", limit=100)
            if not ohlcv:
                continue

            signal = generate_signal(pair["symbol"], ohlcv)
            signal = evaluate_risk(signal)

            # Пропускаем плохие сигналы
            if "❌" in signal["quality"]:
                continue

            text = format_signal_text(signal)
            await message.answer(text, parse_mode="HTML")
            sent += 1
            if sent >= 3:
                break  # пока отправляем не более 3 сигналов
        if sent == 0:
            await message.answer("😕 Подходящих сигналов не найдено.")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при поиске сигналов:\n{e}")

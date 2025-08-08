import asyncio
import datetime
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from utils.trade_tracker import add_open_trade, check_open_trades
import pytz
from db.database import init_db


from config import (
    BOT_TOKEN,
    ADMIN_CHAT_ID,
    CHANNEL_ID,
    MAX_SIGNALS_PER_RUN,
    SIGNAL_INTERVAL_MINUTES
)

from core.bybit_api import BybitAPI
from core.filters import filter_by_volume, apply_all_filters
from core.signal_generator import generate_signal
from core.risk_manager import evaluate_risk
from utils.format_text import format_signal_text
from utils.used_tracker import load_used_today, save_used_today, clear_used_today
from handlers import setup_routers

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def auto_signal_job(bot: Bot):
    print(f"\n🔄 [{datetime.datetime.now().strftime('%H:%M:%S')}] Запуск анализа рынка...")

    api = BybitAPI()
    used_symbols = load_used_today()

    try:
        all_pairs = api.get_usdt_pairs()
        print(f"📊 Всего пар: {len(all_pairs)}")

        filtered = filter_by_volume(all_pairs)
        print(f"✅ После фильтра объёма: {len(filtered)}")

        valid = apply_all_filters(filtered, api.get_ohlcv)
        print(f"🔍 Прошли все фильтры: {len(valid)}\n")

        sent = 0
        for pair in valid:
            symbol = pair["symbol"]

            if symbol in used_symbols:
                print(f"→ {symbol} — ⏩ Уже отправлялся сегодня — пропуск")
                continue

            print(f"→ Анализ пары: {symbol}")
            ohlcv = api.get_ohlcv(symbol, interval="15", limit=200)
            if not ohlcv:
                print(f"  ⚠️ Нет свечей — пропуск")
                continue

            signal = generate_signal(symbol, ohlcv)

            if signal["position"] == "NONE":
                print(f"  ⏹️ Нет сигнала — пропуск")
                continue

            signal = evaluate_risk(signal)

            if "❌" in signal["quality"]:
                print(f"  ❌ Плохой сигнал (rr: {signal['rr_ratio']}) — пропуск")
                continue

            print(f"  ✅ Сигнал найден (rr: {signal['rr_ratio']}) — отправка...")

            text = format_signal_text(signal)
            from utils.logger import log_signal
            log_signal(signal)


            # отправка админу
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="HTML")

            # отправка в канал
            try:
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
            except Exception as e:
                print(f"⚠️ Ошибка отправки в канал: {e}")

            #Добавление в отслеживание
            add_open_trade(signal)

            used_symbols.add(symbol)
            save_used_today(used_symbols)

            sent += 1
            if sent >= MAX_SIGNALS_PER_RUN:
                break

        if sent == 0:
            print("😕 Подходящих сигналов не найдено.")

    except Exception as e:
        print(f"❌ Ошибка автоанализа: {e}")
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"⚠️ Ошибка автоанализа:\n{e}")


def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()

    # 📈 Автоматический анализ каждые N минут
    scheduler.add_job(
        auto_signal_job,
        trigger=IntervalTrigger(minutes=SIGNAL_INTERVAL_MINUTES),
        args=[bot],
        id="auto_signal_job"
    )

    # 🧹 Очистка used_today.json каждый день в 00:00 МСК
    scheduler.add_job(
        clear_used_today,
        trigger=CronTrigger(hour=0, minute=0, timezone=pytz.timezone('Europe/Moscow')),
        id="clear_used_daily"
    )

        # 🔄 Проверка открытых сделок каждые 2 минуты
    scheduler.add_job(
        lambda: check_open_trades(get_price),
        trigger=IntervalTrigger(minutes=2),
        id="check_open_trades"
    )
    from train.auto_retrain import auto_retrain

    # 🧠 Автопереобучение модели каждый день в 01:00 МСК
    scheduler.add_job(
    lambda: asyncio.create_task(auto_retrain(bot)),
    trigger=CronTrigger(hour=1, minute=0, timezone=pytz.timezone('Europe/Moscow')),
    id="auto_retrain"
    )


    scheduler.start()


async def main():
    setup_routers(dp)
    setup_scheduler(bot)

    await auto_signal_job(bot)  # 🔥 Первый запуск сразу
    await dp.start_polling(bot)

def get_price(symbol: str) -> float:
    api = BybitAPI()
    ticker = api.get_ohlcv(symbol, interval="1", limit=1)  # берём 1-мин свечу
    if ticker:
        return float(ticker[-1][4])  # close
    return 0.0


if __name__ == "__main__":
    init_db()  # создаём БД и файлы, если их ещё нет
    asyncio.run(main())  # запускаем бота

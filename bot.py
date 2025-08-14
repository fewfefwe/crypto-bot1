from utils.logging_setup import setup_logging
setup_logging()
import asyncio
import datetime
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
from core.news import news_cache
from apscheduler.triggers.interval import IntervalTrigger
from utils.dataset_logger import log_signal_row, make_signal_id
import logging

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def auto_signal_job(bot: Bot):
    print(f"\n🔄 [{datetime.datetime.now().strftime('%H:%M:%S')}] Запуск анализа рынка...")

    api = BybitAPI()
    used_symbols = load_used_today()

    try:
        all_pairs = api.get_usdt_pairs()
        print(f"📊 Всего валютных пар: {len(all_pairs)}")

        filtered = filter_by_volume(all_pairs)
        print(f"✅ После фильтра объёма: {len(filtered)}")

        valid = apply_all_filters(filtered, api.get_ohlcv)
        print(f"🔍 Прошли все фильтры: {len(valid)}\n")

        sent = 0
        for pair in valid:
            try:
                symbol = pair["symbol"]

                if symbol in used_symbols:
                    print(f"→ {symbol} — ⏩ Уже отправлялся сегодня — пропуск")
                    continue

                print(f"→ Анализ пары: {symbol}")
                ohlcv = api.get_ohlcv(symbol, interval="60", limit=300)
                if not ohlcv:
                    print("  ⚠️ Нет свечей — пропуск")
                    continue

                # новостной фактор
                def news_provider(sym: str) -> float:
                    return news_cache.score(sym)

                signal = generate_signal(
                    symbol,
                    ohlcv,
                    fetcher=api.get_ohlcv,
                    news_score_provider=news_provider
                )

                if signal.get("position") == "NONE":
                    print(f"  ⏹️ Нет сигнала — пропуск ({signal.get('reason','')})")
                    continue

                signal = evaluate_risk(signal)
                if "❌" in signal.get("quality", ""):
                    print(f"  ❌ Плохой сигнал (rr: {signal.get('rr_ratio')}) — пропуск")
                    continue

                # ID сигнала и лог в датасет
                signal_id = make_signal_id(symbol)
                signal["signal_id"] = signal_id
                log_signal_row({
                    "signal_id": signal_id,
                    "ts": datetime.datetime.utcnow().isoformat(),
                    "symbol": symbol,
                    "position": signal["position"],
                    "entry": signal["entry"],
                    "sl": signal["sl"],
                    "tp": signal["tp"],
                    "score": signal.get("score"),
                    "confidence": signal.get("confidence"),
                    "rr_ratio": signal.get("rr_ratio"),
                    "timeframe": "15m",
                    "extras": signal.get("reasons", []),
                })

                # лог в наш файл (не роняем при ошибке)
                try:
                    from utils.logger import log_signal
                    log_signal(signal)
                except Exception as e:
                    print(f"⚠️ log_signal error: {e}")

                # формируем текст (с фоллбеком только при ошибке)
                try:
                    text = format_signal_text(signal)
                except Exception as e:
                    print(f"⚠️ format_signal_text error: {e}")
                    text = (
                        f"📈 {signal.get('symbol')} {signal.get('position')}\n"
                        f"entry: {signal.get('entry')}  tp: {signal.get('tp')}  sl: {signal.get('sl')}\n"
                        f"RR: {signal.get('rr_ratio')}  score: {signal.get('score')}"
                    )

                print(f"  ✅ Сигнал найден (rr: {signal.get('rr_ratio')}) — отправка...")

                # отправка
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode="HTML")
                try:
                    await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
                except Exception as e:
                    print(f"⚠️ Ошибка отправки в канал: {e}")

                # учёт и ограничение количества
                add_open_trade(signal)
                used_symbols.add(symbol)
                save_used_today(used_symbols)

                sent += 1
                if sent >= MAX_SIGNALS_PER_RUN:
                    break

            except Exception as e:
                print(f"⚠️ Ошибка при обработке {pair}: {e}")
                continue

        if sent == 0:
            print("😕 Подходящих сигналов не найдено.")

    except Exception as e:
        print(f"❌ Ошибка автоанализа: {e}")
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"⚠️ Ошибка автоанализа:\n{e}")
        except Exception:
            pass

async def news_refresh_job():
    await news_cache.refresh()


def setup_scheduler(bot: Bot):
    # один планировщик, с дефолтами и таймзоной
    scheduler = AsyncIOScheduler(
        timezone=pytz.timezone('Europe/Moscow'),
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 120
        }
    )

    # флаг конкуренции
    state = {"running": False}

    # обёртка должна быть async, чтобы дождаться завершения и корректно снимать флаг
    async def job_wrapper():
        if state["running"]:
            logging.warning("⏳ Предыдущий анализ ещё не завершён — пропуск.")
            return
        state["running"] = True
        logging.info("🔄 Запуск автоанализа...")
        try:
            await auto_signal_job(bot)
        finally:
            state["running"] = False

    # автоанализ по интервалу
    scheduler.add_job(
        job_wrapper,
        trigger=IntervalTrigger(minutes=SIGNAL_INTERVAL_MINUTES),
        id="auto_signal_job",
        replace_existing=True
    )

    # очистка used_today в 00:00 МСК
    scheduler.add_job(
        clear_used_today,
        trigger=CronTrigger(hour=0, minute=0, timezone=pytz.timezone('Europe/Moscow')),
        id="clear_used_daily",
        replace_existing=True
    )

    # проверка открытых сделок каждые 2 мин
    scheduler.add_job(
        lambda: check_open_trades(get_price),
        trigger=IntervalTrigger(minutes=2),
        id="check_open_trades",
        replace_existing=True
    )

    # новости каждые 5 мин
    scheduler.add_job(
    news_refresh_job,
    trigger=IntervalTrigger(minutes=5),
    id="news_refresh",
    replace_existing=True
    )

    # автопереобучение в 01:00 МСК
    from train.auto_retrain import auto_retrain
    scheduler.add_job(
        lambda: asyncio.create_task(auto_retrain(bot)),
        trigger=CronTrigger(hour=1, minute=0, timezone=pytz.timezone('Europe/Moscow')),
        id="auto_retrain",
        replace_existing=True
    )

    scheduler.start()

    job = scheduler.get_job("auto_signal_job")
    logging.info(f"🕒 auto_signal_job: interval={SIGNAL_INTERVAL_MINUTES}m, next_run={job.next_run_time}")

    return scheduler



async def main():
    setup_routers(dp)
    setup_scheduler(bot)
    # не запускаем вручную auto_signal_job — пусть идёт по расписанию
    # await auto_signal_job(bot)
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

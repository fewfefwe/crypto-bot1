import pandas as pd
import os
from datetime import datetime, timedelta

LOG_FILE = "signals_log.csv"

def load_signals():
    """Загружаем логи сигналов в DataFrame"""
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=[
            "datetime", "symbol", "position", "entry", "tp", "sl",
            "leverage", "risk", "status", "profit_%", "closed_at"
        ])
    
    df = pd.read_csv(LOG_FILE)
    # Преобразуем даты
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["closed_at"] = pd.to_datetime(df["closed_at"])
    return df

def calculate_statistics(period: str = "day") -> dict:
    """
    Возвращает статистику за выбранный период
    period: day / week / month
    """
    df = load_signals()
    if df.empty:
        return {
            "signals": 0,
            "positive": 0,
            "negative": 0,
            "profit_percent": 0.0
        }
    
    now = datetime.now()
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(weeks=1)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:
        raise ValueError("Неверный период. Используй day/week/month.")
    
    # Фильтруем по дате закрытия
    df_period = df[df["closed_at"] >= start_date]
    
    if df_period.empty:
        return {
            "signals": 0,
            "positive": 0,
            "negative": 0,
            "profit_percent": 0.0
        }
    
    # Считаем статистику
    signals = len(df_period)
    positive = len(df_period[df_period["profit_%"] > 0])
    negative = len(df_period[df_period["profit_%"] < 0])
    profit_percent = df_period["profit_%"].sum()

    return {
        "signals": signals,
        "positive": positive,
        "negative": negative,
        "profit_percent": round(profit_percent, 2)
    }

def format_statistics(period: str = "day") -> str:
    """Форматирует статистику в красивый текст"""
    stats = calculate_statistics(period)

    period_name = {
        "day": "день",
        "week": "неделю",
        "month": "месяц"
    }.get(period, period)

    return (
        f"📊 Статистика за {period_name}\n"
        f"▫️ Прибыльность: {stats['profit_percent']}%\n"
        f"▫️ Количество сигналов: {stats['signals']}\n"
        f"▫️ Положительных сделок: {stats['positive']}\n"
        f"▫️ Отрицательных сделок: {stats['negative']}"
    )

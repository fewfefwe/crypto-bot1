# statistics.py
import pandas as pd
import os
from datetime import datetime, timedelta

TRADES_FILE  = "trades_log.csv"    # новый формат из trade_tracker
SIGNALS_FILE = "signals_log.csv"   # устаревший (если вдруг есть)

def _load_trades_df() -> pd.DataFrame:
    """
    Пробуем загрузить trades_log.csv (новый формат).
    Если его нет — пробуем signals_log.csv (старый формат) и приводим к общему виду.
    Возвращаем DF с колонками: closed_at (datetime), pnl_pct (float), status (str)
    и дополнительной инфой.
    """
    # 1) Новый формат
    if os.path.exists(TRADES_FILE):
        df = pd.read_csv(TRADES_FILE)
        # ожидаемые поля: signal_id,symbol,position,entry,tp,sl,risk_pct,leverage,rr_ratio,
        #                 opened_at,closed_at,status,closed_price,pnl_pct
        # Парсим даты
        for col in ("opened_at", "closed_at"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        # Гарантируем нужные поля
        if "pnl_pct" not in df.columns:
            df["pnl_pct"] = 0.0
        if "status" not in df.columns:
            df["status"] = ""
        return df

    # 2) Старый формат (если вдруг он появится)
    if os.path.exists(SIGNALS_FILE):
        df = pd.read_csv(SIGNALS_FILE)
        # ожидаемые поля: datetime,symbol,position,entry,tp,sl,risk,leverage,status,profit_%,closed_at
        # Приводим к формату нового:
        if "profit_%" in df.columns and "pnl_pct" not in df.columns:
            df["pnl_pct"] = pd.to_numeric(df["profit_%"], errors="coerce")
        for col in ("datetime", "closed_at"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        # Если нет closed_at — примем datetime как closed_at
        if "closed_at" not in df.columns and "datetime" in df.columns:
            df["closed_at"] = df["datetime"]
        if "status" not in df.columns:
            df["status"] = ""
        # Переименуем для совместимости
        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "opened_at"})
        # гарантируем столбцы
        if "pnl_pct" not in df.columns:
            df["pnl_pct"] = 0.0
        return df

    # 3) Нет файлов — пустой каркас
    return pd.DataFrame(columns=[
        "signal_id","symbol","position","entry","tp","sl","risk_pct","leverage","rr_ratio",
        "opened_at","closed_at","status","closed_price","pnl_pct"
    ])

def calculate_statistics(period: str = "day") -> dict:
    """
    Статистика по закрытым сделкам за период: day / week / month
    """
    df = _load_trades_df()
    if df.empty:
        return {"signals": 0, "positive": 0, "negative": 0, "profit_percent": 0.0}

    # Берём ТОЛЬКО закрытые сделки (есть closed_at)
    if "closed_at" in df.columns:
        df = df[df["closed_at"].notna()].copy()
    if df.empty:
        return {"signals": 0, "positive": 0, "negative": 0, "profit_percent": 0.0}

    now = datetime.now()
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(weeks=1)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:
        # на всякий случай — дефолт: 7 дней
        start_date = now - timedelta(days=7)

    # Фильтр по дате закрытия
    df_period = df[df["closed_at"] >= start_date]
    if df_period.empty:
        return {"signals": 0, "positive": 0, "negative": 0, "profit_percent": 0.0}

    # Счётчики
    signals = len(df_period)
    # положительные/отрицательные по pnl_pct
    if "pnl_pct" in df_period.columns:
        positive = int((df_period["pnl_pct"] > 0).sum())
        negative = int((df_period["pnl_pct"] < 0).sum())
        profit_percent = float(df_period["pnl_pct"].sum())
    else:
        positive = negative = 0
        profit_percent = 0.0

    return {
        "signals": signals,
        "positive": positive,
        "negative": negative,
        "profit_percent": round(profit_percent, 2),
    }

def format_statistics(period: str = "day") -> str:
    stats = calculate_statistics(period)
    period_name = {"day": "день", "week": "неделю", "month": "месяц"}.get(period, period)
    return (
        f"📊 Статистика за {period_name}\n"
        f"▫️ Прибыльность: {stats['profit_percent']}%\n"
        f"▫️ Количество закрытых сделок: {stats['signals']}\n"
        f"▫️ Положительных: {stats['positive']}\n"
        f"▫️ Отрицательных: {stats['negative']}"
    )

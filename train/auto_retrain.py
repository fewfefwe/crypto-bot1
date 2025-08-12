import os
import io
import shutil
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from aiogram import Bot
from config import ADMIN_CHAT_ID

SIGNALS_FILE = Path("signals_log.csv")
TRADES_FILE  = Path("trades_log.csv")
MODEL_DIR    = Path("model")
SCALER_PATH  = MODEL_DIR / "scaler.pkl"
MODEL_PATH   = MODEL_DIR / "signal_model.pkl"

MIN_SAMPLES = 80  # минимум примеров для тренировки

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _backup_if_exists(path: Path):
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak_{ts}")
        shutil.copy2(path, backup)
        return backup
    return None

def _build_features(df_sig: pd.DataFrame) -> pd.DataFrame:
    """
    Делает числовые фичи из лога сигналов.
    Допускает отсутствие некоторых колонок — заполняем NaN/0.
    """
    out = pd.DataFrame(index=df_sig.index)

    # Бинарный признак направления
    pos = df_sig.get("position", pd.Series(index=df_sig.index, dtype=object)).astype(str).str.upper()
    out["is_long"]  = (pos == "LONG").astype(int)
    out["is_short"] = (pos == "SHORT").astype(int)

    # Базовые числовые признаки
    for col in ["entry", "sl", "tp", "score", "confidence", "rr_ratio"]:
        out[col] = pd.to_numeric(df_sig.get(col, 0), errors="coerce").fillna(0.0)

    # Инженерия отношений
    out["risk_abs"] = (out["entry"] - out["sl"]).abs()
    out["tp_dist"]  = (out["tp"] - out["entry"]).abs()

    # Защита от деления на ноль
    denom = out["risk_abs"].replace(0, np.nan)
    out["rr_calc"] = (out["tp_dist"] / denom).fillna(0.0)

    # Нормализуем confidence (если задан 0..100)
    if out["confidence"].max() > 1.0:
        out["confidence"] = out["confidence"] / 100.0

    # Можно добавить ещё: час дня, день недели, и т.п., если они есть в логе
    return out

async def auto_retrain(bot: Bot):
    # 0) Проверки наличия файлов
    if not SIGNALS_FILE.exists():
        msg = "⚠️ Для переобучения нет файла signals_log.csv."
        print(msg); await bot.send_message(ADMIN_CHAT_ID, msg); return
    if not TRADES_FILE.exists():
        msg = "⚠️ Для переобучения нет файла trades_log.csv."
        print(msg); await bot.send_message(ADMIN_CHAT_ID, msg); return

    # 1) Загрузка датасетов
    try:
        df_sig = pd.read_csv(SIGNALS_FILE)
        df_trd = pd.read_csv(TRADES_FILE)
    except Exception as e:
        msg = f"⚠️ Ошибка чтения логов: {e}"
        print(msg); await bot.send_message(ADMIN_CHAT_ID, msg); return

    # 2) Проверка необходимых полей
    need_sig = {"signal_id", "position", "entry", "sl", "tp"}
    need_trd = {"signal_id", "pnl_pct"}
    if not need_sig.issubset(df_sig.columns):
        msg = f"⚠️ В signals_log.csv нет нужных колонок: {need_sig - set(df_sig.columns)}"
        print(msg); await bot.send_message(ADMIN_CHAT_ID, msg); return
    if not need_trd.issubset(df_trd.columns):
        msg = f"⚠️ В trades_log.csv нет нужных колонок: {need_trd - set(df_trd.columns)}"
        print(msg); await bot.send_message(ADMIN_CHAT_ID, msg); return

    # 3) Склейка по signal_id (inner join — берём только те, у кого есть исход)
    df = pd.merge(df_sig, df_trd, on="signal_id", how="inner", suffixes=("_sig", "_trd"))
    if len(df) < MIN_SAMPLES:
        msg = f"⚠️ Недостаточно примеров для переобучения: {len(df)} < {MIN_SAMPLES}"
        print(msg); await bot.send_message(ADMIN_CHAT_ID, msg); return

    # 4) Метка класса из результата сделки
    y = (pd.to_numeric(df["pnl_pct"], errors="coerce").fillna(0.0) > 0.0).astype(int)

    # 5) Фичи
    X = _build_features(df)

    # 6) Тренировочное/тестовое разбиение
    X_train, X_test, y_train, y_test = train_test_split(
        X.values, y.values, test_size=0.2, random_state=42, stratify=y.values
    )

    # 7) Скейлер и модель
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    model = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        max_iter=600,
        random_state=42
    )
    model.fit(X_train_scaled, y_train)

    acc = float(model.score(X_test_scaled, y_test))
    await bot.send_message(ADMIN_CHAT_ID, f"✅ Переобучение завершено. Точность на тесте: {acc:.2%}")

    # 8) Бэкап старых моделей и сохранение новых
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    b1 = _backup_if_exists(MODEL_PATH)
    b2 = _backup_if_exists(SCALER_PATH)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    msg = "📦 Модели обновлены: signal_model.pkl и scaler.pkl"
    if b1 or b2:
        msg += f"\n🗂 Бэкапы: {b1.name if b1 else ''} {b2.name if b2 else ''}".strip()
    await bot.send_message(ADMIN_CHAT_ID, msg)

    # 9) (опционально) Горячая перезагрузка модели, если добавишь reload_model() в core/signal_generator.py
    try:
        from core.signal_generator import reload_model  # добавь функцию (ниже)
        reload_model()
        await bot.send_message(ADMIN_CHAT_ID, "♻️ Модель перезагружена в рантайме без рестарта.")
    except Exception:
        # если функции нет — просто молчим; модель подхватится после рестарта процесса
        pass

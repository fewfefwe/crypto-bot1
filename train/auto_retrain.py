import pandas as pd
import os
import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from datetime import datetime
from config import ADMIN_CHAT_ID
from aiogram import Bot

LOG_FILE = "signals_log.csv"
MODEL_DIR = "model"

async def auto_retrain(bot: Bot):
    if not os.path.exists(LOG_FILE):
        msg = "⚠️ Нет логов сигналов для переобучения."
        print(msg)
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
        return

    df = pd.read_csv(LOG_FILE)
    
    # Проверяем наличие нужных колонок
    if not {"symbol", "profit_%", "position"}.issubset(df.columns):
        msg = "⚠️ Недостаточно данных для переобучения."
        print(msg)
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
        return

    # Формируем label: 1 = прибыльная сделка, 0 = убыточная
    df["label"] = (df["profit_%"] > 0).astype(int)

    # Удаляем лишние столбцы
    X = df.drop(columns=[
        "datetime", "symbol", "position", "status", "closed_at", "label"
    ], errors="ignore")
    y = df["label"]

    if len(X) < 50:  # Минимум 50 сделок для обучения
        msg = "⚠️ Недостаточно данных (<50) для переобучения."
        print(msg)
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
        return

    # Масштабирование
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Разделение на train/test
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

    # Обучение нейросети
    model = MLPClassifier(hidden_layer_sizes=(64, 32), activation='relu', max_iter=500, random_state=42)
    model.fit(X_train, y_train)

    acc = model.score(X_test, y_test)
    msg = f"✅ Модель переобучена! Точность на тесте: {acc:.2%}"
    print(msg)
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)

    # Сохраняем новые версии модели
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, os.path.join(MODEL_DIR, "signal_model.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))

    done_msg = f"📦 Модель обновлена {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} МСК"
    print(done_msg)
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=done_msg)

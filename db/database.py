import sqlite3
import os
from datetime import datetime
from cryptography.fernet import Fernet

DB_FILE = "database.db"
KEY_FILE = "db_secret.key"

# ----------------- Шифрование API ключей -----------------
# Создаём ключ шифрования, если его ещё нет
if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, "rb") as f:
    SECRET_KEY = f.read()

fernet = Fernet(SECRET_KEY)


def encrypt(text: str) -> str:
    return fernet.encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()


# ----------------- Работа с БД -----------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date TEXT,
            subscription_type TEXT,
            subscription_end TEXT,
            trading_enabled INTEGER DEFAULT 0
        )
    """)

    # Таблица ключей Bybit
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT,
            api_secret TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    # Таблица оплат
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            tariff TEXT,
            start_date TEXT,
            end_date TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ База данных и таблицы инициализированы")


# ----------------- Функции для работы с пользователями -----------------

def add_user(user_id: int, username: str):
    """Добавляет нового пользователя, если его ещё нет в БД"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if user is None:
        cursor.execute("""
            INSERT INTO users (user_id, username, join_date, subscription_type, subscription_end, trading_enabled)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "none", None, 0))
        conn.commit()
        print(f"👤 Пользователь {username} добавлен в базу.")
    conn.close()


def has_active_subscription(user_id: int) -> bool:
    """Проверяем, есть ли у пользователя активная подписка"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        end_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        return end_date > datetime.now()
    return False


# ----------------- Функции для работы с API ключами -----------------

def set_api_keys(user_id: int, api_key: str, api_secret: str):
    """Сохраняем зашифрованные ключи Bybit"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    enc_key = encrypt(api_key)
    enc_secret = encrypt(api_secret)

    cursor.execute("""
        INSERT OR REPLACE INTO api_keys (user_id, api_key, api_secret, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, enc_key, enc_secret, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    print(f"🔑 API ключи сохранены для пользователя {user_id}")


def get_api_keys(user_id: int):
    """Возвращает расшифрованные ключи Bybit"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT api_key, api_secret FROM api_keys WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return decrypt(row[0]), decrypt(row[1])
    return None, None


def delete_api_keys(user_id: int):
    """Удаляет ключи Bybit (отключает автоторговлю)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
    cursor.execute("UPDATE users SET trading_enabled = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"❌ API ключи удалены для пользователя {user_id}")

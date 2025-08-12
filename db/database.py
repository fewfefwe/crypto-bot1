# db/database.py — расширенная версия (подписки + автоторговля + настройки)

import sqlite3
import os
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

DB_FILE = "database.db"
KEY_FILE = "db_secret.key"

# ----------------- Шифрование API ключей -----------------
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

# ----------------- Вспомогательное -----------------
def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def _column_exists(cursor, table: str, col: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cursor.fetchall())

# ----------------- Инициализация / миграции -----------------
def init_db():
    conn = _connect()
    c = conn.cursor()

    # users (твоя текущая схема + мягкие миграции)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date TEXT,
            subscription_type TEXT,
            subscription_end TEXT,
            trading_enabled INTEGER DEFAULT 0
        )
    """)
    # добавим безопасно новые колонки при необходимости
    if not _column_exists(c, "users", "subscription_type"):
        c.execute("ALTER TABLE users ADD COLUMN subscription_type TEXT")
    if not _column_exists(c, "users", "subscription_end"):
        c.execute("ALTER TABLE users ADD COLUMN subscription_end TEXT")
    if not _column_exists(c, "users", "trading_enabled"):
        c.execute("ALTER TABLE users ADD COLUMN trading_enabled INTEGER DEFAULT 0")

    # api_keys (твоя)
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT,
            api_secret TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    # payments (твоя)
    c.execute("""
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

    # NEW: доплата за автоторговлю
    c.execute("""
        CREATE TABLE IF NOT EXISTS autotrade_addon (
            user_id INTEGER PRIMARY KEY,
            paid_until TEXT,      -- ISO datetime; NULL = не оплачен
            is_enabled INTEGER DEFAULT 0, -- 0/1 тумблер
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    # NEW: пользовательские настройки автоторговли
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            risk_pct REAL DEFAULT 1.0,         -- риск на сделку, %
            leverage INTEGER DEFAULT 5,        -- плечо
            margin_mode TEXT DEFAULT 'ISOLATED',   -- ISOLATED|CROSS
            position_mode TEXT DEFAULT 'ONEWAY',   -- ONEWAY|HEDGE
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ База данных и таблицы инициализированы")

# ----------------- Пользователи -----------------
def add_user(user_id: int, username: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone() is None:
        c.execute("""
            INSERT INTO users (user_id, username, join_date, subscription_type, subscription_end, trading_enabled)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, _now(), "none", None, 0))
        # создать базовые записи под настройки/автоторговлю
        c.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        c.execute("INSERT OR IGNORE INTO autotrade_addon (user_id, paid_until, is_enabled) VALUES (?, ?, ?)",
                  (user_id, None, 0))
        conn.commit()
        print(f"👤 Пользователь {username} добавлен в базу.")
    conn.close()

def has_active_subscription(user_id: int) -> bool:
    end = get_subscription_expiry(user_id)
    return (end is not None) and (end > datetime.now())

def get_subscription_expiry(user_id: int):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row["subscription_end"]:
        try:
            return datetime.strptime(row["subscription_end"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    return None

# ----------------- Подписки (сигналы) -----------------
def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def activate_subscription(user_id: int, plan: str, amount: float = 0.0):
    """
    plan: 'WEEK' | 'MONTH' | 'QUARTER'
    Проставит users.subscription_type, users.subscription_end и создаст запись в payments.
    """
    plan = plan.upper()
    if plan == "WEEK":
        delta = timedelta(weeks=1)
        tariff_label = "1_WEEK"
    elif plan == "MONTH":
        delta = timedelta(days=30)
        tariff_label = "1_MONTH"
    elif plan == "QUARTER":
        delta = timedelta(days=90)
        tariff_label = "3_MONTHS"
    else:
        raise ValueError("Unknown plan")

    start = datetime.now()
    end = start + delta

    conn = _connect()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET subscription_type = ?, subscription_end = ?
        WHERE user_id = ?
    """, (plan, end.strftime("%Y-%m-%d %H:%M:%S"), user_id))

    c.execute("""
        INSERT INTO payments (user_id, amount, tariff, start_date, end_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, amount, tariff_label, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ----------------- Автоторговля: оплата и тумблер -----------------
def autotrade_paid(user_id: int) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT paid_until FROM autotrade_addon WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row["paid_until"]:
        try:
            return datetime.strptime(row["paid_until"], "%Y-%m-%d %H:%M:%S") > datetime.now()
        except Exception:
            return False
    return False

def set_autotrade_paid(user_id: int, days: int):
    """Оплатить автоторговлю на N дней (напр., days=30)."""
    start = datetime.now()
    end = start + timedelta(days=days)
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO autotrade_addon (user_id, paid_until, is_enabled) VALUES (?, ?, ?)",
              (user_id, None, 0))
    c.execute("UPDATE autotrade_addon SET paid_until = ? WHERE user_id = ?",
              (end.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

def autotrade_enabled(user_id: int) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT is_enabled FROM autotrade_addon WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row["is_enabled"])

def toggle_autotrade(user_id: int, enable: bool):
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO autotrade_addon (user_id, paid_until, is_enabled) VALUES (?, ?, ?)",
              (user_id, None, 0))
    c.execute("UPDATE autotrade_addon SET is_enabled = ? WHERE user_id = ?", (1 if enable else 0, user_id))
    conn.commit()
    conn.close()

# ----------------- API ключи (Bybit) -----------------
def set_api_keys(user_id: int, api_key: str, api_secret: str):
    conn = _connect()
    c = conn.cursor()
    enc_key = encrypt(api_key)
    enc_secret = encrypt(api_secret)
    c.execute("""
        INSERT OR REPLACE INTO api_keys (user_id, api_key, api_secret, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, enc_key, enc_secret, _now()))
    conn.commit()
    conn.close()
    print(f"🔑 API ключи сохранены для пользователя {user_id}")

def get_api_keys(user_id: int):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT api_key, api_secret FROM api_keys WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return decrypt(row["api_key"]), decrypt(row["api_secret"])
    return None, None

def delete_api_keys(user_id: int):
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
    c.execute("UPDATE users SET trading_enabled = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"❌ API ключи удалены для пользователя {user_id}")

# ----------------- Настройки пользователя (риск/плечо/режимы) -----------------
def get_user_settings(user_id: int) -> dict:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"risk_pct": 1.0, "leverage": 5, "margin_mode": "ISOLATED", "position_mode": "ONEWAY"}
    return dict(row)

def update_user_settings(user_id: int, *, risk_pct=None, leverage=None, margin_mode=None, position_mode=None):
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
    if risk_pct is not None:
        c.execute("UPDATE user_settings SET risk_pct = ? WHERE user_id = ?", (float(risk_pct), user_id))
    if leverage is not None:
        c.execute("UPDATE user_settings SET leverage = ? WHERE user_id = ?", (int(leverage), user_id))
    if margin_mode is not None:
        c.execute("UPDATE user_settings SET margin_mode = ? WHERE user_id = ?", (str(margin_mode), user_id))
    if position_mode is not None:
        c.execute("UPDATE user_settings SET position_mode = ? WHERE user_id = ?", (str(position_mode), user_id))
    conn.commit()
    conn.close()

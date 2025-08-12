import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

MAX_SIGNALS_PER_RUN = int(os.getenv("MAX_SIGNALS_PER_RUN", "1"))
SIGNAL_INTERVAL_MINUTES = int(os.getenv("SIGNAL_INTERVAL_MINUTES", "15"))

VOLUME_MIN = int(os.getenv("VOLUME_MIN", "50000000"))
VOLUME_MAX = int(os.getenv("VOLUME_MAX", "300000000"))

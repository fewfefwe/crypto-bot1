# handlers/__init__.py

from aiogram import Dispatcher

# роутеры экранов
from .start import router as start_router
from .signals import router as signals_router
from .stats import router as stats_router

# админ-команды для выдачи подписки/автоторговли (из admin_sub.py)
from .admin_sub import router as admin_router

def setup_routers(dp: Dispatcher):
    """Подключаем все роутеры бота (порядок важен только для перехватчиков)."""
    dp.include_router(admin_router)     # /sub_week, /sub_month, /auto_on, ...
    dp.include_router(start_router)     # /start и меню
    dp.include_router(signals_router)   # раздел «Сигналы»
    dp.include_router(stats_router)     # статистика

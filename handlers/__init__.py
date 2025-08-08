from .start import router as start_router
from .signals import router as signal_router
from .stats import router as stats_router

def setup_routers(dp):
    """Подключаем все роутеры бота"""
    dp.include_router(start_router)    # /start
    dp.include_router(signal_router)   # обработка сигналов
    dp.include_router(stats_router)    # статистика /stats

import logging

def setup_logging():
    # Базовая настройка — показываем всё с INFO и выше
    logging.basicConfig(
        level=logging.INFO,  # <--- раньше было WARNING
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Наши логи — INFO (чтобы видеть весь процесс)
    for name in ["app", "core", "core.signal_generator"]:
        logging.getLogger(name).setLevel(logging.INFO)

    # Можно оставить предупреждения от сторонних библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)  # пусть пишет расписание
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pybit").setLevel(logging.WARNING)

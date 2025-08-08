import json
import os
import datetime

USED_FILE = "used_today.json"

def load_used_today() -> set:
    if not os.path.exists(USED_FILE):
        return set()
    with open(USED_FILE, "r") as f:
        try:
            data = json.load(f)
            return set(data.get(str(datetime.date.today()), []))
        except Exception:
            return set()

def save_used_today(used: set):
    # Загружаем всё
    all_data = {}
    if os.path.exists(USED_FILE):
        try:
            with open(USED_FILE, "r") as f:
                all_data = json.load(f)
        except Exception:
            all_data = {}

    # Обновляем только для сегодняшнего дня
    all_data[str(datetime.date.today())] = list(used)

    with open(USED_FILE, "w") as f:
        json.dump(all_data, f, indent=2)

def clear_used_today():
    with open(USED_FILE, "w") as f:
        json.dump([], f)
    print("🧹 used_today.json очищен автоматически.")

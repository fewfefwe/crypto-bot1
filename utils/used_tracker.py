import json
import os
import datetime
from typing import Set, Dict, List

USED_FILE = "used_today.json"

def _today_key() -> str:
    return str(datetime.date.today())

def _load_all() -> Dict[str, List[str]]:
    if not os.path.exists(USED_FILE):
        return {}
    try:
        with open(USED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def load_used_today() -> Set[str]:
    data = _load_all()
    return set(data.get(_today_key(), []))

def save_used_today(used: Set[str]) -> None:
    data = _load_all()
    data[_today_key()] = sorted(list(used))
    # опционально чистим записи старше 7 дней
    try:
        today = datetime.date.today()
        for k in list(data.keys()):
            d = datetime.date.fromisoformat(k)
            if (today - d).days > 7:
                data.pop(k, None)
    except Exception:
        pass

    with open(USED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clear_used_today() -> None:
    """Очищаем только сегодняшние пары, не ломая формат файла."""
    data = _load_all()
    data[_today_key()] = []
    with open(USED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("🧹 used_today.json: очищен список для сегодняшней даты.")

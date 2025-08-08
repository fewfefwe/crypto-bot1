from typing import List, Dict
import numpy as np
from config import VOLUME_MIN, VOLUME_MAX


VOLUME_MIN = 50_000_000
VOLUME_MAX = 300_000_000

def filter_by_volume(pairs: List[Dict]) -> List[Dict]:
    """
    Убирает монеты с неподходящим объёмом
    """
    return [
        p for p in pairs
        if VOLUME_MIN <= p["volume_24h"] <= VOLUME_MAX
    ]

def is_sideways(ohlcv: List[List], threshold=0.01) -> bool:
    """
    Определяет боковик:
    - Разница между max и min ценой слишком мала
    """
    closes = [float(candle[4]) for candle in ohlcv]  # цена закрытия
    max_close = max(closes)
    min_close = min(closes)
    change = (max_close - min_close) / min_close

    return change < threshold  # если меньше 1%, считаем боковиком

def is_highly_volatile(ohlcv: List[List], threshold=0.06) -> bool:
    """
    Определяет высокую волатильность:
    - Разница между high и low свеч слишком большая
    """
    for candle in ohlcv:
        high = float(candle[2])
        low = float(candle[3])
        if (high - low) / low > threshold:
            return True
    return False

def apply_all_filters(pairs: List[Dict], get_ohlcv_func) -> List[Dict]:
    """
    Применяет все фильтры и возвращает только нормальные пары
    :param pairs: список пар после фильтрации по объёму
    :param get_ohlcv_func: функция, которая возвращает свечи по символу
    """
    result = []

    for pair in pairs:
        ohlcv = get_ohlcv_func(pair["symbol"], interval="15", limit=100)
        if not ohlcv:
            continue

        if is_sideways(ohlcv):
            continue
        if is_highly_volatile(ohlcv):
            continue

        result.append(pair)

    return result

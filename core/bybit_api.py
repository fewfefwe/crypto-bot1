from pybit.unified_trading import HTTP
from typing import List, Dict
from config import BYBIT_API_KEY, BYBIT_API_SECRET
from pybit.unified_trading import HTTP

class BybitAPI:
    def __init__(self):
        self.session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET, testnet=False)

    def get_usdt_pairs(self) -> List[Dict]:
        """
        Получает список всех USDT-пар с данными по объёму и цене
        """
        result = self.session.get_tickers(category="linear")  # linear = фьючерсы
        tickers = result.get("result", {}).get("list", [])

        filtered = [
            {
                "symbol": t["symbol"],
                "volume_24h": float(t["turnover24h"]),
                "price": float(t["lastPrice"])
            }
            for t in tickers
            if t["symbol"].endswith("USDT")
        ]

        return filtered

    def get_ohlcv(self, symbol: str, interval="60", limit=100) -> List[List]:
        """
        Получает OHLCV данные по символу
        :param symbol: торговая пара (например BTCUSDT)
        :param interval: таймфрейм (1 = 1м, 60 = 1ч и т.д.)
        :param limit: количество свечей
        """
        result = self.session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return result.get("result", {}).get("list", [])

import re
import asyncio
import aiohttp
import time
from typing import Dict, List

RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
    "https://www.theblock.co/rss",
]

# очень простой лексикон; позже можно заменить на VADER/TextBlob
POS_WORDS = {"partnership", "integration", "launch", "upgrade", "approval", "etf", "listing",
             "funding", "adoption", "milestone", "burn", "buyback", "staking", "ecosystem", "surge"}
NEG_WORDS = {"hack", "exploit", "lawsuit", "ban", "fine", "outage", "delist", "sell-off",
             "regulation", "downtime", "breach", "shutdown", "liquidation", "insolvency"}

# базовое сопоставление тикеров → ключевых слов/брендов
SYMBOL_MAP: Dict[str, List[str]] = {
    "BTCUSDT": ["bitcoin", "btc"],
    "ETHUSDT": ["ethereum", "eth"],
    "BNBUSDT": ["bnb", "binance coin", "binance"],
    "SOLUSDT": ["sol", "solana"],
    "XRPUSDT": ["xrp", "ripple"],
    "ADAUSDT": ["ada", "cardano"],
    "DOGEUSDT": ["doge", "dogecoin"],
    "TONUSDT": ["ton", "toncoin", "telegram open network"],
    # добавляй по мере надобности...
}

def _clean(txt: str) -> str:
    return re.sub(r"\s+", " ", txt.lower()).strip()

def _sentiment(text: str) -> float:
    """возвращает 0..1 (0 — плохо, 1 — хорошо)"""
    t = _clean(text)
    pos = sum(1 for w in POS_WORDS if w in t)
    neg = sum(1 for w in NEG_WORDS if w in t)
    if pos == 0 and neg == 0:
        return 0.5
    raw = (pos - neg) / max(1, pos + neg)
    return max(0.0, min(1.0, 0.5 + 0.5 * raw))

class NewsCache:
    def __init__(self):
        self._scores: Dict[str, float] = {}
        self._last_update = 0

    def score(self, symbol: str) -> float:
        return float(self._scores.get(symbol, 0.5))

    async def refresh(self, timeout: int = 10):
        now = time.time()
        if now - self._last_update < 60:  # антиспам обновлений
            return
        self._last_update = now

        scores: Dict[str, List[float]] = {sym: [] for sym in SYMBOL_MAP}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as sess:
            for url in RSS_FEEDS:
                try:
                    async with sess.get(url) as r:
                        text = await r.text()
                except Exception:
                    continue
                # простенький парс — ищем <title>...</title>
                titles = re.findall(r"<title>(.*?)</title>", text, flags=re.I | re.S)
                for title in titles[:150]:  # не увлекаться
                    t = _clean(re.sub("<.*?>", "", title))
                    s = _sentiment(t)
                    for sym, keys in SYMBOL_MAP.items():
                        if any(k in t for k in keys):
                            scores.setdefault(sym, []).append(s)

        # усредним; если новостей нет — 0.5
        self._scores = {sym: (sum(vals)/len(vals) if vals else 0.5) for sym, vals in scores.items()}

# создаём глобальный экземпляр
news_cache = NewsCache()

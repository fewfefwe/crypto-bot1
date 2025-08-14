import math
import logging
from typing import List, Dict, Callable, Optional

import numpy as np
import pandas as pd
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import MFIIndicator, OnBalanceVolumeIndicator, VolumeWeightedAveragePrice
import joblib
import torch

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---- Настройки под 1H ----
BASE_TF = "60"       # 1H
MTF_TF  = "240"      # 4H подтверждение тренда
PROB_THRESHOLD = 0.60
SCORE_THRESHOLD = 75   # чуть выше, т.к. хотим избирательность на 1H
MIN_CANDLES    = 260   # чтобы уверенно считать EMA200/RSI/BB и т.д.
MAX_VOL_RATIO  = 20.0

# ---- Модель (опционально) ----
try:
    scaler = joblib.load("model/scaler.pkl")
    model  = joblib.load("model/signal_model.pkl")
    _model_ok = True
    logger.info("Models loaded: scaler.pkl, signal_model.pkl")
except Exception as e:
    _model_ok = False
    logger.warning(f"Models not loaded, fallback to rules only: {e}")

def _normalize_ohlcv(ohlcv_raw):
    out = []
    for r in ohlcv_raw or []:
        if isinstance(r, dict):
            ts = r.get("timestamp") or r.get("start") or r.get("open_time") or r.get("t")
            o  = r.get("open") or r.get("o")
            h  = r.get("high") or r.get("h")
            l  = r.get("low")  or r.get("l")
            c  = r.get("close") or r.get("c")
            v  = r.get("volume") or r.get("v") or r.get("vol")
        else:
            if len(r) < 6:
                continue
            ts, o, h, l, c, v = r[0], r[1], r[2], r[3], r[4], r[5]
        if ts is None or o is None or h is None or l is None or c is None or v is None:
            continue
        out.append([ts, o, h, l, c, v])
    return out

def _fib_pullback_score(close, swing_low, swing_high, side: str) -> float:
    if swing_high <= swing_low:
        return 0.0
    fib382 = swing_high - 0.382 * (swing_high - swing_low)
    fib500 = swing_high - 0.500 * (swing_high - swing_low)
    fib618 = swing_high - 0.618 * (swing_high - swing_low)
    if side == "SHORT":
        fib382 = swing_low + 0.382 * (swing_high - swing_low)
        fib500 = swing_low + 0.500 * (swing_high - swing_low)
        fib618 = swing_low + 0.618 * (swing_high - swing_low)
    lo, hi = (min(fib618, fib382), max(fib618, fib382))
    if close < lo or close > hi:
        band = abs(close - fib500) / (abs(hi - lo) + 1e-9)
        return float(max(0.0, 1.0 - band*2.0))
    return 1.0

def reload_model():
    global scaler, model, _model_ok
    try:
        scaler = joblib.load("model/scaler.pkl")
        model  = joblib.load("model/signal_model.pkl")
        _model_ok = True
        logger.info("Models reloaded from disk.")
    except Exception as e:
        _model_ok = False
        logger.warning(f"Reload failed: {e}")

def generate_signal(
    symbol: str,
    ohlcv: List[List],
    fetcher: Optional[Callable[[str, str, int], List[List]]] = None,
    news_score_provider: Optional[Callable[[str], float]] = None
) -> Dict:
    """Базовый анализ на 1H, подтверждение тренда по 4H, цель 3–4%."""
    try:
        norm = _normalize_ohlcv(ohlcv)
        if not norm or len(norm) < MIN_CANDLES:
            return {"symbol": symbol, "position": "NONE", "reason": f"few_candles:{len(norm) if norm else 0}"}

        df = pd.DataFrame(norm, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.sort_values("timestamp")
        df[["open","high","low","close","volume"]] = df[["open","high","low","close","volume"]].astype(float)

        # ==== Индикаторы (1H) ====
        df["ema50"]  = EMAIndicator(close=df["close"], window=50).ema_indicator()
        df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()
        macd = MACD(close=df["close"], window_fast=12, window_slow=26, window_sign=9)
        df["macd"]        = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"]   = df["macd"] - df["macd_signal"]
        df["rsi"]   = RSIIndicator(close=df["close"], window=14).rsi()
        df["atr"]   = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range()
        df["adx"]   = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14).adx()
        df["mfi"]   = MFIIndicator(high=df["high"], low=df["low"], close=df["close"], volume=df["volume"], window=14).money_flow_index()
        df["obv"]   = OnBalanceVolumeIndicator(close=df["close"], volume=df["volume"]).on_balance_volume()
        vwap        = VolumeWeightedAveragePrice(high=df["high"], low=df["low"], close=df["close"], volume=df["volume"], window=20)
        df["vwap"]  = vwap.volume_weighted_average_price()
        bb          = BollingerBands(close=df["close"], window=20, window_dev=2)
        df["bb_bw"] = (bb.bollinger_hband() - bb.bollinger_lband()) / (df["close"] + 1e-9)
        df["vol_ma20"]  = df["volume"].rolling(20, min_periods=20).mean()
        df["vol_z"]     = (df["volume"] - df["vol_ma20"]) / (df["vol_ma20"].rolling(100).std(ddof=0) + 1e-9)
        df["vol_ratio"] = df["volume"] / (df["vol_ma20"] + 1e-9)

        latest = df.iloc[-1]

        # ==== MTF подтверждение (4H EMA50>EMA200 для LONG и наоборот для SHORT) ====
        mtf_ok = None
        if fetcher is not None:
            raw_4h = fetcher(symbol, MTF_TF, 260)
            h4n = _normalize_ohlcv(raw_4h) if raw_4h else []
            if len(h4n) >= 60:
                h4 = pd.DataFrame(h4n, columns=["ts","o","h","l","c","v"]).astype(float)
                ema50_h4  = EMAIndicator(close=h4["c"], window=50).ema_indicator().iloc[-1]
                ema200_h4 = EMAIndicator(close=h4["c"], window=200).ema_indicator().iloc[-1]
                mtf_ok = (ema50_h4 > ema200_h4)

        # ==== Кандидат направления ====
        trend_up   = latest["ema50"] > latest["ema200"]
        trend_down = latest["ema50"] < latest["ema200"]
        macd_bull  = latest["macd"]  > latest["macd_signal"]
        macd_bear  = latest["macd"]  < latest["macd_signal"]

        candidate = "LONG" if (trend_up and macd_bull) else ("SHORT" if (trend_down and macd_bear) else None)
        if candidate is None:
            return {"symbol": symbol, "position": "NONE", "reason": "no_consensus"}

        # ==== Фибо-откат на 1H ====
        lookback = 180
        swing_high = float(df["high"].iloc[-lookback:].max())
        swing_low  = float(df["low"].iloc[-lookback:].min())
        fib_score  = _fib_pullback_score(float(latest["close"]), swing_low, swing_high, candidate)

        # ==== Скоринг ====
        score = 0.0
        weights = {
            "trend": 25,  "macd": 15, "adx": 10, "rsi": 10,
            "vwap": 10,   "volume": 10, "bb": 5, "fib": 10, "mtf": 5
        }

        score += weights["trend"]
        if (candidate == "LONG" and latest["macd_hist"] > 0) or (candidate == "SHORT" and latest["macd_hist"] < 0):
            score += weights["macd"]
        if latest["adx"] >= 18:
            score += weights["adx"]
        if (candidate == "LONG" and latest["rsi"] > 50) or (candidate == "SHORT" and latest["rsi"] < 50):
            score += weights["rsi"]
        if (candidate == "LONG" and latest["close"] > latest["vwap"]) or (candidate == "SHORT" and latest["close"] < latest["vwap"]):
            score += weights["vwap"]

        vol_ratio = min(MAX_VOL_RATIO, float(latest["vol_ratio"]))
        if vol_ratio > 1.5 or float(latest["vol_z"]) > 1.0:
            score += weights["volume"]

        bb_now = float(latest["bb_bw"])
        bb_med = float(df["bb_bw"].rolling(200).median().iloc[-1])
        if bb_now < bb_med * 0.8:
            if (candidate == "LONG" and latest["close"] > bb.bollinger_hband().iloc[-1]) or \
               (candidate == "SHORT" and latest["close"] < bb.bollinger_lband().iloc[-1]):
                score += weights["bb"]

        score += weights["fib"] * float(fib_score)
        if mtf_ok is not None and ((candidate == "LONG" and mtf_ok) or (candidate == "SHORT" and not mtf_ok)):
            score += weights["mtf"]

        # ==== Новостной бонус (по желанию) ====
        if news_score_provider:
            ns = float(news_score_provider(symbol))  # 0..1
            score += 10.0 * (max(0.0, ns - 0.5) * 2 if candidate == "LONG" else max(0.0, 0.5 - ns) * 2)
            score = min(100.0, score)

        # ==== Модель (если есть) ====
        nn_prob = None
        if _model_ok:
            try:
                feat_names = ["close","ema50","ema200","macd","macd_signal","rsi","vol_ratio"]
                X = pd.DataFrame([[ 
                    latest["close"], latest["ema50"], latest["ema200"],
                    latest["macd"], latest["macd_signal"], latest["rsi"], vol_ratio
                ]], columns=feat_names)
                if hasattr(scaler, "feature_names_in_"):
                    for col in scaler.feature_names_in_:
                        if col not in X.columns:
                            X[col] = 0.0
                    X = X[scaler.feature_names_in_]
                X_scaled = scaler.transform(X)
                with torch.no_grad():
                    pred = model(torch.tensor(X_scaled, dtype=torch.float32))
                    try: pred = pred.sigmoid()
                    except Exception: pass
                    nn_prob = float(pred.squeeze().item())
                if nn_prob < PROB_THRESHOLD:
                    return {"symbol": symbol, "position": "NONE", "reason": f"low_prob:{nn_prob:.3f}"}
                score += 10.0 * (nn_prob - PROB_THRESHOLD) / max(1e-6, 1 - PROB_THRESHOLD)
                score = min(100.0, score)
            except Exception as e:
                logger.warning(f"NN skipped: {e}")
                nn_prob = None

        # ==== Финальное решение ====
        if score < SCORE_THRESHOLD:
            return {"symbol": symbol, "position": "NONE", "reason": f"low_score:{score:.1f}"}

        entry = float(latest["close"])
        atr   = float(latest["atr"]) if not math.isnan(latest["atr"]) else 0.0

        # Цели под 1H: держим ориентир 3–4%,
        # но ещё сравниваем с 2*ATR, чтобы на «тихих» инструментах цель не была слишком маленькой.
        pct_tp = 0.035   # 3.5% средняя цель
        pct_sl = 0.015   # 1.5% защитный стоп (RR около 2)
        if candidate == "LONG":
            tp = max(entry * (1 + pct_tp), entry + 2 * atr)
            sl = min(entry * (1 - pct_sl), entry - 1 * atr)
        else:
            tp = min(entry * (1 - pct_tp), entry - 2 * atr)
            sl = max(entry * (1 + pct_sl), entry + 1 * atr)

        out = {
            "symbol": symbol,
            "position": candidate,
            "entry": round(entry, 6),
            "tp": round(tp, 6),
            "sl": round(sl, 6),
            "confidence": round((nn_prob or 0.8) * 100, 2),
            "score": round(score, 1),
            "timeframe": "1H",
        }
        logger.info(f"[{symbol}] {candidate} score={score:.1f} entry={out['entry']} tp={out['tp']} sl={out['sl']}")
        return out

    except Exception as e:
        logger.exception(f"[{symbol}] generate_signal error: {e}")
        return {"symbol": symbol, "position": "NONE", "error": str(e)}

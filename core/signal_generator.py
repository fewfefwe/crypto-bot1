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

# ---- Порог/настройки ----
PROB_THRESHOLD = 0.60         # если используем твою NN
SCORE_THRESHOLD = 70          # итоговый скор для сигнала (0..100)
MIN_CANDLES    = 220
MAX_VOL_RATIO  = 20.0

# ---- Загрузка модели (не обязательно) ----
try:
    scaler = joblib.load("model/scaler.pkl")
    model  = joblib.load("model/signal_model.pkl")
    _model_ok = True
    logger.info("Models loaded: scaler.pkl, signal_model.pkl")
except Exception as e:
    _model_ok = False
    logger.warning(f"Models not loaded, fallback to rules only: {e}")

def _normalize_ohlcv(ohlcv_raw):
    """
    Приводит любые варианты OHLCV к списку [ts, open, high, low, close, volume].
    Игнорируем лишние поля (если их 7+), поддерживаем как списки, так и dict.
    """
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
            # r — это список/кортеж; берём первые 6 полей
            # Bybit часто отдаёт 7, где 6-е или 7-е — лишнее, поэтому просто режем.
            if len(r) < 6:
                continue
            ts, o, h, l, c, v = r[0], r[1], r[2], r[3], r[4], r[5]
        # защита от None
        if ts is None or o is None or h is None or l is None or c is None or v is None:
            continue
        out.append([ts, o, h, l, c, v])
    return out


def _safe(v, name, reasons):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        reasons.append(f"nan:{name}")
        return None
    return v

def _fib_pullback_score(close, swing_low, swing_high, side: str) -> float:
    """Возвращает 0..1 — насколько близко цена к «правильной» зоне Фибо для входа."""
    if swing_high <= swing_low:
        return 0.0
    # уровни для лонга (откат вниз в ап-тренде)
    fib382 = swing_high - 0.382 * (swing_high - swing_low)
    fib500 = swing_high - 0.500 * (swing_high - swing_low)
    fib618 = swing_high - 0.618 * (swing_high - swing_low)

    # для шорта зеркалим
    if side == "SHORT":
        fib382 = swing_low + 0.382 * (swing_high - swing_low)
        fib500 = swing_low + 0.500 * (swing_high - swing_low)
        fib618 = swing_low + 0.618 * (swing_high - swing_low)

    # чем ближе к диапазону 0.382..0.618, тем выше балл
    lo, hi = (min(fib618, fib382), max(fib618, fib382))
    if close < lo or close > hi:
        # небольшое послабление около 0.5
        band = abs(close - fib500) / (abs(hi - lo) + 1e-9)
        return float(max(0.0, 1.0 - band*2.0))
    # внутри коридора — максимальный балл
    return 1.0

def reload_model():
    """Горячая перезагрузка весов после автотренировки."""
    global scaler, model, _model_ok
    try:
        new_scaler = joblib.load("model/scaler.pkl")
        new_model  = joblib.load("model/signal_model.pkl")
        scaler[:] = new_scaler  # если хочешь, но проще так:
        scaler = new_scaler
        model  = new_model
        _model_ok = True
        logger.info("Models reloaded from disk.")
    except Exception as e:
        _model_ok = False
        logger.warning(f"Reload failed: {e}")


def generate_signal(
    symbol: str,
    ohlcv: List[List],
    fetcher: Optional[Callable[[str, str, int], List[List]]] = None,  # например api.get_ohlcv
    news_score_provider: Optional[Callable[[str], float]] = None      # 0..1 (негатив..позитив)
) -> Dict:
    """
    Улучшенная стратегия:
      - индикаторы тренда/моментума/объёма
      - фибо-откат с конгруэнтностью
      - мульти-таймфрейм: 1h тренд (если fetcher передан)
      - скоринг 0..100; сигнал при SCORE_THRESHOLD+
    """
    reasons: List[str] = []
    try:
        if ohlcv is None or len(ohlcv) < MIN_CANDLES:
            return {"symbol": symbol, "position": "NONE", "reason": f"few_candles:{len(ohlcv) if ohlcv else 0}"}

        norm = _normalize_ohlcv(ohlcv)
        if len(norm) < MIN_CANDLES:
            return {"symbol": symbol, "position": "NONE", "reason": f"few_candles:{len(norm)}"}

        df = pd.DataFrame(norm, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.sort_values("timestamp")
        df[["open","high","low","close","volume"]] = df[["open","high","low","close","volume"]].astype(float)

        # ==== Индикаторы (15m по умолчанию) ====
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

        bb = BollingerBands(close=df["close"], window=20, window_dev=2)
        df["bb_bw"] = (bb.bollinger_hband() - bb.bollinger_lband()) / (df["close"] + 1e-9)  # относительная ширина

        df["vol_ma20"] = df["volume"].rolling(20, min_periods=20).mean()
        df["vol_z"]    = (df["volume"] - df["vol_ma20"]) / (df["vol_ma20"].rolling(100).std(ddof=0) + 1e-9)
        df["vol_ratio"]= df["volume"] / (df["vol_ma20"] + 1e-9)

        latest = df.iloc[-1]

        # ==== Мульти-таймфрейм (1h тренд), если fetcher есть ====
        mtf_ok = None
        if fetcher is not None:
            h1 = fetcher(symbol, "60", 220)  # 1-часовые свечи
            if h1 and len(h1) >= 60:
        # нормализуем как и 15m
                h1n = _normalize_ohlcv(h1)
            if len(h1n) >= 60:
                h1df = pd.DataFrame(h1n, columns=["ts","o","h","l","c","v"]).astype(float)
                ema50_h1  = EMAIndicator(close=h1df["c"], window=50).ema_indicator().iloc[-1]
                ema200_h1 = EMAIndicator(close=h1df["c"], window=200).ema_indicator().iloc[-1]
                mtf_ok = (ema50_h1 > ema200_h1)  # True = бычий часовой тренд


        # ==== Направление (кандидат) ====
        trend_up   = latest["ema50"] > latest["ema200"]
        trend_down = latest["ema50"] < latest["ema200"]
        macd_bull  = latest["macd"]  > latest["macd_signal"]
        macd_bear  = latest["macd"]  < latest["macd_signal"]

        candidate = None
        if trend_up and macd_bull:
            candidate = "LONG"
        elif trend_down and macd_bear:
            candidate = "SHORT"

        if candidate is None:
            return {"symbol": symbol, "position": "NONE", "reason": "no_consensus"}

        # ==== Фибо: берём свинг за последние N баров ====
        lookback = 120
        swing_high = float(df["high"].iloc[-lookback:].max())
        swing_low  = float(df["low"].iloc[-lookback:].min())
        fib_score  = _fib_pullback_score(float(latest["close"]), swing_low, swing_high, candidate)  # 0..1

        # ==== Скоpинг: собираем баллы ====
        score = 0.0
        weights = {
            "trend": 25,      # EMA50/200 согласованность
            "macd": 15,       # MACD & hist
            "adx": 10,        # сила тренда
            "rsi": 10,        # >50 long / <50 short
            "vwap": 10,       # цена выше/ниже VWAP
            "volume": 10,     # surge по объёму
            "bb": 5,          # сужение полос + выход
            "fib": 10,        # pullback в зоне 0.382..0.618
            "mtf": 5,         # 1h тренд в ту же сторону (если есть)
        }

        # trend
        score += weights["trend"]

        # macd
        if (candidate == "LONG" and latest["macd_hist"] > 0) or (candidate == "SHORT" and latest["macd_hist"] < 0):
            score += weights["macd"]

        # adx
        if latest["adx"] >= 18:
            score += weights["adx"]

        # rsi
        if (candidate == "LONG" and latest["rsi"] > 50) or (candidate == "SHORT" and latest["rsi"] < 50):
            score += weights["rsi"]

        # vwap
        if (candidate == "LONG" and latest["close"] > latest["vwap"]) or (candidate == "SHORT" and latest["close"] < latest["vwap"]):
            score += weights["vwap"]

        # volume surge
        vol_ratio = min(MAX_VOL_RATIO, float(latest["vol_ratio"]))
        if vol_ratio > 1.5 or float(latest["vol_z"]) > 1.0:
            score += weights["volume"]

        # bollinger squeeze breakout (узкие полосы + движение в сторону)
        bb_now = float(latest["bb_bw"])
        bb_med = float(df["bb_bw"].rolling(200).median().iloc[-1])
        if bb_now < bb_med * 0.8:  # сжатие
            if (candidate == "LONG" and latest["close"] > bb.bollinger_hband().iloc[-1]) or \
               (candidate == "SHORT" and latest["close"] < bb.bollinger_lband().iloc[-1]):
                score += weights["bb"]

        # fib confluence
        score += weights["fib"] * float(fib_score)

        # MTF
        if mtf_ok is not None and ((candidate == "LONG" and mtf_ok) or (candidate == "SHORT" and not mtf_ok)):
            score += weights["mtf"]

        # ==== Новостной фактор (опционально) ====
        news_bonus = 0.0
        if news_score_provider:
            ns = float(news_score_provider(symbol))  # ожидаем 0..1
            # для лонга нас интересуют положительные новости, для шорта — отрицательные
            if candidate == "LONG":
                news_bonus = 10.0 * max(0.0, ns - 0.5) * 2  # 0..10
            else:
                news_bonus = 10.0 * max(0.0, (0.5 - ns)) * 2
            score += news_bonus

        # ==== Нейросетка как дополнительный вес (если есть) ====
                # ==== Нейросетка как дополнительный вес (если есть) ====
        nn_prob = None
        if _model_ok:
            try:
                # наши текущие фичи
                feat_names = ["close","ema50","ema200","macd","macd_signal","rsi","vol_ratio"]
                X = pd.DataFrame([[ 
                    latest["close"], latest["ema50"], latest["ema200"],
                    latest["macd"], latest["macd_signal"], latest["rsi"], vol_ratio
                ]], columns=feat_names)

                # если scaler обучался с именованными колонками — выравниваем
                if hasattr(scaler, "feature_names_in_"):
                    # добьём недостающие нулями
                    for col in scaler.feature_names_in_:
                        if col not in X.columns:
                            X[col] = 0.0
                    # оставим только те, на которых учился scaler, и в нужном порядке
                    X = X[scaler.feature_names_in_]

                # а если имён нет, но число фич не совпало — отключаем модель
                if hasattr(scaler, "n_features_in_") and X.shape[1] != getattr(scaler, "n_features_in_", X.shape[1]):
                    raise ValueError(f"feature_mismatch: X={X.shape[1]} vs scaler={scaler.n_features_in_}")

                X_scaled = scaler.transform(X)
                with torch.no_grad():
                    pred = model(torch.tensor(X_scaled, dtype=torch.float32))
                    try:
                        pred = pred.sigmoid()
                    except Exception:
                        pass
                    nn_prob = float(pred.squeeze().item())

                if nn_prob < PROB_THRESHOLD:
                    return {"symbol": symbol, "position": "NONE", "reason": f"low_prob:{nn_prob:.3f}"}

                score += 10.0 * (nn_prob - PROB_THRESHOLD) / max(1e-6, 1 - PROB_THRESHOLD)
                score = min(100.0, score)

            except Exception as e:
                logger.warning(f"NN skipped (mismatch or error): {e}")
                nn_prob = None  # продолжаем по правилам


        # ==== финальное решение ====
        if score < SCORE_THRESHOLD:
            return {"symbol": symbol, "position": "NONE", "reason": f"low_score:{score:.1f}"}

        entry = float(latest["close"])
        atr   = float(latest["atr"]) if not math.isnan(latest["atr"]) else 0.0
        tp = entry + 2 * atr if candidate == "LONG" else entry - 2 * atr
        sl = entry - 1 * atr if candidate == "LONG" else entry + 1 * atr

        out = {
            "symbol": symbol,
            "position": candidate,
            "entry": round(entry, 4),
            "tp": round(tp, 4),
            "sl": round(sl, 4),
            "confidence": round((nn_prob or 0.8) * 100, 2),
            "score": round(score, 1),
            "reasons": [] if not reasons else reasons,
        }
        logger.info(f"[{symbol}] {candidate} score={score:.1f} nn={nn_prob} entry={out['entry']}")
        return out

    except Exception as e:
        logger.exception(f"[{symbol}] generate_signal error: {e}")
        return {"symbol": symbol, "position": "NONE", "error": str(e)}
    
    

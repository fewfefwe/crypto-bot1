# core/risk_manager.py
from typing import Dict, Optional

DEFAULT_SETTINGS = {
    "risk_pct": 1.0,          # риск на сделку в %
    "leverage": 5,            # дефолтное плечо
    "margin_mode": "ISOLATED",
    "position_mode": "ONEWAY",
}

def evaluate_risk(signal: Dict, user_settings: Optional[Dict] = None) -> Dict:
    """
    Дополняет сигнал расчётом RR и безопасными дефолтами.
    НЕ требует наличия signal['risk'].
    """
    s = {**DEFAULT_SETTINGS, **(user_settings or {})}

    entry = float(signal["entry"])
    sl    = float(signal["sl"])
    tp    = float(signal["tp"])

    risk_per_unit = abs(entry - sl)
    reward        = abs(tp - entry)
    rr            = reward / (risk_per_unit + 1e-9)

    if rr >= 2.0:
        quality = f"✅ RR {rr:.2f}"
    elif rr >= 1.2:
        quality = f"⚠️ RR {rr:.2f}"
    else:
        quality = f"❌ RR {rr:.2f}"

    signal.update({
        "rr_ratio": round(rr, 2),
        "quality": quality,
        # дефолтные трейдинг-настройки (не зависят от входящего signal)
        "leverage": s["leverage"],
        "risk_pct": s["risk_pct"],
        "margin_mode": s["margin_mode"],
        "position_mode": s["position_mode"],
    })
    return signal

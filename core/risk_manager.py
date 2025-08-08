from typing import Dict

def evaluate_risk(signal: Dict) -> Dict:
    """
    Рассчитывает RR, динамический риск (%) и подбирает плечо от 7x до 15x.
    """

    entry = signal["entry"]
    tp = signal["tp"]
    sl = signal["sl"]

    if signal["position"] == "LONG":
        profit = tp - entry
        risk = entry - sl
    else:
        profit = entry - tp
        risk = sl - entry

    if risk <= 0:
        rr_ratio = 0
        signal.update({
            "rr_ratio": 0,
            "risk_percent": 0,
            "recommended_leverage": 7,
            "quality": "❌ Неверный стоп"
        })
        return signal

    rr_ratio = round(profit / risk, 2)

    # Подбор наилучшего плеча в диапазоне 7–15
    best_leverage = 7
    risk_percent = 0

    for lev in range(7, 16):
        percent = round((risk / entry) * 100 * lev, 2)
        if percent <= 100:
            best_leverage = lev
            risk_percent = percent
            break
    else:
        # если все плечи дают риск >100%, берём минимальное
        best_leverage = 7
        risk_percent = round((risk / entry) * 100 * best_leverage, 2)

    # Оценка качества
    if rr_ratio >= 2.0:
        quality = "✅ Сделка: стоит входить"
    elif rr_ratio >= 1.0:
        quality = "⚠️ Сделка: средняя"
    else:
        quality = "❌ Сделка: невыгодная"

    signal.update({
        "rr_ratio": rr_ratio,
        "risk_percent": risk_percent,
        "recommended_leverage": best_leverage,
        "quality": quality
    })

    return signal

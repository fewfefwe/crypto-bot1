def format_signal_text(signal: dict) -> str:
    if signal['position'] == "NONE":
        return "❌ Сигнал не найден."

    text = (
        f"<b>📡 Торговый сигнал</b>\n"
        f"<b>Монета:</b> <code>{signal['symbol']}</code>\n"
        f"<b>Позиция:</b> <b>{signal['position']}</b>\n"
        f"<b>Точка входа:</b> <code>{signal['entry']}</code>\n"
        f"<b>Take Profit:</b> <code>{signal['tp']}</code>\n"
        f"<b>Stop Loss:</b> <code>{signal['sl']}</code>\n"
        f"<b>Плечо:</b> <code>{signal['leverage']}</code>\n"
        f"<b>Риск сделки:</b> <code>{signal['risk']}</code>\n"
        f"<b>RR Ratio:</b> <code>{signal['rr_ratio']}</code>\n"
        f"{signal['quality']}"
    )
    return text


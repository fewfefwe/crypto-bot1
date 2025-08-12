def format_signal_text(signal: dict) -> str:
    if signal.get('position') == "NONE":
        return "❌ Сигнал не найден."

    leverage = signal.get('leverage', '—')
    risk_pct = signal.get('risk_pct', '—')
    rr_ratio = signal.get('rr_ratio', '—')
    quality  = signal.get('quality', '')

    return (
        f"<b>📡 Торговый сигнал</b>\n"
        f"<b>Монета:</b> <code>{signal.get('symbol', '—')}</code>\n"
        f"<b>Позиция:</b> <b>{signal.get('position', '—')}</b>\n"
        f"<b>Точка входа:</b> <code>{signal.get('entry', '—')}</code>\n"
        f"<b>Take Profit:</b> <code>{signal.get('tp', '—')}</code>\n"
        f"<b>Stop Loss:</b> <code>{signal.get('sl', '—')}</code>\n"
        f"<b>Плечо:</b> <code>{leverage}</code>\n"
        f"<b>Риск сделки:</b> <code>{risk_pct}%</code>\n"
        f"<b>RR Ratio:</b> <code>{rr_ratio}</code>\n"
        f"{quality}"
    )

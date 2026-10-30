"""Pure notification formatting; does not contact Telegram or imply delivery."""


def signal_preview(signal):
    return {
        "event_id": signal["event_id"],
        "channel": "telegram",
        "delivery_status": "PREVIEW_ONLY",
        "authorized": False,
        "text": (
            "HALAL QUANT · إشارة بحثية\n"
            f"{signal['symbol']} · {signal['timeframe']}\n"
            f"{signal['strategy']} · {signal['action']}\n"
            f"وقت الشمعة: {signal['bar_time']}\n"
            "ليست إذن تداول. يلزم اجتياز ضوابط البيانات والامتثال والمخاطر."
        ),
    }

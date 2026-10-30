"""Pure localized notification formatting; never contacts Telegram."""


def signal_preview(signal, language="en"):
    if language not in ("en", "ar"):
        raise ValueError("Unsupported preview language")
    common = (
        f"{signal['symbol']} · {signal['timeframe']}\n{signal['strategy']} · {signal['action']}\n"
    )
    texts = {
        "en": (
            "HALAL QUANT · Research signal\n"
            + common
            + f"Bar close: {signal['bar_time']}\n"
            + "Not trading authorization. Data, compliance and risk controls must pass."
        ),
        "ar": (
            "HALAL QUANT · إشارة بحثية\n"
            + common
            + f"وقت الشمعة: {signal['bar_time']}\n"
            + "ليست إذن تداول. يلزم اجتياز ضوابط البيانات والامتثال والمخاطر."
        ),
    }
    return {
        "event_id": signal["event_id"],
        "channel": "telegram",
        "delivery_status": "PREVIEW_ONLY",
        "authorized": False,
        "language": language,
        "text": texts[language],
        "texts": texts,
    }

"""Telegram transport. Never include raw API errors or token-bearing URLs in logs."""

import httpx


class Telegram:
    def __init__(self, token, client=None):
        if not token:
            raise ValueError("Configure TELEGRAM_BOT_TOKEN on the server")
        self.base = "https://api.telegram.org/bot" + token + "/"
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)

    def call(self, method, payload):
        return self.client.post(self.base + method, json=payload)

    def verified(self, method, payload):
        try:
            response = self.call(method, payload)
            data = response.json()
            if (
                not isinstance(data, dict)
                or response.status_code != 200
                or data.get("ok") is not True
            ):
                raise ValueError("Telegram verification failed")
            return data["result"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise ValueError("Telegram verification unavailable") from None

    def close(self):
        self.client.close()

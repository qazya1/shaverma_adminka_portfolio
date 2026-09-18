"""Minimal Telegram client for the admin panel's own bot.

This is intentionally a separate bot/token from the main shaverma
customer-facing bot (ADMIN_TELEGRAM_BOT_TOKEN), and it currently does
exactly one thing: deliver a login OTP code to an administrator's chat.
The bot token is read from settings and is never logged.

api.telegram.org is unreachable directly from some hosting locations,
so every call optionally goes through TELEGRAM_PROXY_URL (http(s):// or
socks5://) if one is configured -- unset, this behaves exactly as
before (a direct connection).
"""

import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class TelegramDeliveryError(RuntimeError):
    """Raised when the Telegram API call fails or is rejected."""


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.telegram_api_base_url.rstrip("/")

    def send_login_code(self, telegram_user_id: str, code: str) -> None:
        """Send a login OTP code to the given admin's Telegram account.

        `telegram_user_id` is the admin's numeric Telegram user id
        (AdminUser.telegram_user_id). The Bot API's own `sendMessage`
        parameter is called `chat_id`, but for a private bot<->user chat
        it is numerically identical to the user id, so no separate chat
        id needs to be stored or resolved.

        Never log `code`, and never let the bot token leak into logs or
        exception messages -- httpx errors are caught and re-raised with a
        generic message.
        """

        url = f"{self._base_url}/bot{self._settings.admin_telegram_bot_token}/sendMessage"
        text = f"Shaverma Admin: your login code is {code}. It expires in a few minutes."

        try:
            with httpx.Client(proxy=self._settings.telegram_proxy_url, timeout=10.0) as client:
                response = client.post(url, json={"chat_id": telegram_user_id, "text": text})
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Telegram delivery failed for telegram_user_id=%s", telegram_user_id)
            raise TelegramDeliveryError("Failed to deliver login code via Telegram") from exc

        if not payload.get("ok", False):
            logger.warning("Telegram API rejected sendMessage for telegram_user_id=%s", telegram_user_id)
            raise TelegramDeliveryError("Telegram API rejected the message")

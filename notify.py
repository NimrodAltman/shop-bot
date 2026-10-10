"""
notify.py
=========
One-way admin alerts, sent as a Telegram message from the bot to its own
developer. Used for things the developer should know about but the user
never sees: an Anthropic API failure, a new order coming in.

Deliberately dependency-free (stdlib ``urllib`` only, no ``requests``) and
never raises — a failed alert must never break the user-facing conversation.
Silently does nothing if ``ADMIN_TELEGRAM_ID`` isn't set, so it's optional
exactly like the Supabase configuration in db.py.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")


def send_admin_alert(message: str) -> None:
    """Send a message to the developer's own Telegram chat, best-effort."""
    if not TELEGRAM_TOKEN or not ADMIN_TELEGRAM_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": ADMIN_TELEGRAM_ID, "text": f"🤖 ShopBot Alert:\n{message}"}).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=5)
    except Exception as exc:
        logger.warning("Admin alert failed to send: %s", exc)

"""
[NOTIFIER SERVICE] Mobile Alert Gateway
=======================================
Sends real-time push notifications to the user's mobile device.
Currently implements Telegram Bot API.
"""

import os
import json
import asyncio
import logging
import urllib.request
from app.core.config import settings

logger = logging.getLogger("notifier")

class NotifierService:
    def __init__(self):
        self.telegram_token = settings.TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = settings.TELEGRAM_CHAT_ID
        
        if not self.telegram_token or not self.telegram_chat_id:
            logger.warning("[NOTIFIER] Telegram credentials missing in .env. Mobile alerts disabled.")

    def _send_sync(self, url: str, payload: dict):
        """Synchronous sender using standard urllib to avoid aiohttp dependency."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status
        except Exception as e:
            logger.error(f"[NOTIFIER] Exception sending Telegram alert: {e}")
            return 500

    async def send_telegram_alert(self, message: str):
        """Sends a message via Telegram asynchronously."""
        if not self.telegram_token or not self.telegram_chat_id:
            return
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        # Run blocking network call in thread
        status = await asyncio.to_thread(self._send_sync, url, payload)
        if status == 200:
            logger.info("[NOTIFIER] Telegram alert sent successfully.")
        else:
            logger.warning(f"[NOTIFIER] Telegram alert failed with status {status}")

notifier_service = NotifierService()

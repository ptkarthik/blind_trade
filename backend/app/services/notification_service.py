import os
import requests
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Handles sending mobile notifications via Telegram and WhatsApp (Twilio).
    """
    
    def __init__(self):
        # Telegram configs
        self.telegram_bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        self.telegram_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", None)
        
        # WhatsApp Twilio configs
        self.twilio_account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        self.twilio_auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        self.twilio_whatsapp_from = getattr(settings, "TWILIO_WHATSAPP_FROM", None) # e.g. "whatsapp:+14155238886"
        self.twilio_whatsapp_to = getattr(settings, "TWILIO_WHATSAPP_TO", None) # e.g. "whatsapp:+919876543210"

    def send_mobile_alert(self, message: str):
        """Sends the message to all configured notification channels."""
        logger.info(f"📱 Sending Mobile Alert: {message}")
        
        self.send_telegram_alert(message)
        self.send_whatsapp_alert(message)

    def send_telegram_alert(self, message: str):
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info("✅ Telegram alert sent successfully.")
            else:
                logger.error(f"❌ Failed to send Telegram alert: {response.text}")
        except Exception as e:
            logger.error(f"❌ Error sending Telegram alert: {e}")

    def send_whatsapp_alert(self, message: str):
        if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_whatsapp_from, self.twilio_whatsapp_to]):
            return

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
            payload = {
                "From": self.twilio_whatsapp_from,
                "To": self.twilio_whatsapp_to,
                "Body": message
            }
            response = requests.post(
                url, 
                data=payload, 
                auth=(self.twilio_account_sid, self.twilio_auth_token),
                timeout=5
            )
            if response.status_code in [200, 201]:
                logger.info("✅ WhatsApp alert sent successfully.")
            else:
                logger.error(f"❌ Failed to send WhatsApp alert: {response.text}")
        except Exception as e:
            logger.error(f"❌ Error sending WhatsApp alert: {e}")

notification_service = NotificationService()

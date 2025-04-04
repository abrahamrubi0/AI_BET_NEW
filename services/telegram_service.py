# services/telegram_service.py
import json
import requests
from typing import Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

def send_telegram_message(bot_token: str, chat_id: str, data: Dict[str, Any]) -> bool:
    """
    Envía `data` a Telegram formateado en JSON.
    """
    try:
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        formatted_json = json.dumps(data, indent=4, default=str)

        payload = {
            "chat_id": chat_id,
            "text": f"📊 *Match update:*\n```json\n{formatted_json}\n```",
            "parse_mode": "Markdown"
        }

        response = requests.post(telegram_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Mensaje enviado a Telegram con éxito.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje a Telegram: {str(e)}")
        return False

def send_error_notification(bot_token: str, chat_id: str, message: str) -> bool:
    """Envía un mensaje de error a Telegram."""
    return send_telegram_message(bot_token, chat_id, {"critical": message})

# /root/pbot/src/pbot/utils/telegram.py
import requests
import logging
import os

logger = logging.getLogger(__name__)

def send_message(bot_token, chat_id, message):
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot-Token oder Chat-ID nicht konfiguriert.")
        return

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Wir nutzen HTML, das ist viel robuster als MarkdownV2
    # und verhindert 400 Bad Request Fehler bei Preisen mit Punkten.
    payload = {
        'chat_id': chat_id, 
        'text': message, 
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }

    try:
        response = requests.post(api_url, data=payload, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Netzwerkfehler beim Senden der Telegram-Nachricht: {e}")
        # Bei 400 Errors (Formatierung) loggen wir die Antwort für Debugging
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Telegram Antwort: {e.response.text}")
    except Exception as e:
        logger.error(f"Allgemeiner Fehler beim Senden der Telegram-Nachricht: {e}")


def send_document(bot_token, chat_id, file_path, caption=""):
    """Sendet ein Dokument (z.B. eine CSV-Datei) an einen Telegram-Chat."""
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot-Token oder Chat-ID nicht konfiguriert.")
        return

    api_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    # Auch hier HTML für die Caption nutzen
    payload = {
        'chat_id': chat_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }

    try:
        with open(file_path, 'rb') as doc:
            files = {'document': doc}
            # Timeout erhöht für Uploads
            response = requests.post(api_url, data=payload, files=files, timeout=30)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Fehler beim Senden des Dokuments: {e}")

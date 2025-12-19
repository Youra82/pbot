import requests
import json
import os
import sys

# --- Konfiguration ---
# Wir suchen die secret.json im gleichen Ordner
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_FILE = os.path.join(BASE_DIR, 'secret.json')

def load_secrets():
    print(f"Lese Konfiguration aus: {SECRET_FILE}")
    if not os.path.exists(SECRET_FILE):
        print("❌ FEHLER: secret.json nicht gefunden!")
        return None, None
    
    try:
        with open(SECRET_FILE, 'r') as f:
            secrets = json.load(f)
            
        tg_conf = secrets.get('telegram', {})
        token = tg_conf.get('bot_token')
        chat = tg_conf.get('chat_id')
        
        if not token or not chat:
            print("❌ FEHLER: 'bot_token' oder 'chat_id' fehlen in secret.json")
            print(f"Gefunden - Token: {'Ja' if token else 'Nein'}, Chat ID: {'Ja' if chat else 'Nein'}")
            return None, None
            
        return token, chat
    except Exception as e:
        print(f"❌ FEHLER beim Lesen der JSON: {e}")
        return None, None

def send_test_msg(token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Test-Nachricht mit HTML (genau wie im Bot)
    message = (
        "<b>🔔 PBot Test-Nachricht</b>\n\n"
        "Wenn du das lesen kannst, funktioniert die Verbindung!\n"
        "<i>Modus: HTML</i>\n"
        "Status: ✅ Online"
    )
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    print(f"\nSende Nachricht an Chat-ID: {chat_id}...")
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        
        if response.status_code == 200:
            print("✅ ERFOLG! Nachricht wurde gesendet.")
            print("Bitte prüfe deine Telegram App.")
        else:
            print(f"❌ FEHLER: Telegram API antwortete mit Code {response.status_code}")
            print(f"Antwort-Text: {response.text}")
            
    except Exception as e:
        print(f"❌ KRITISCHER FEHLER beim Senden: {e}")

if __name__ == "__main__":
    bot_token, chat_id = load_secrets()
    if bot_token and chat_id:
        send_test_msg(bot_token, chat_id)

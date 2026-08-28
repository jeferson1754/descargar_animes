import os
import requests
import logging


def enviar_mensaje_telegram(mensaje):
    """
    Envía una notificación de texto a tu chat de Telegram usando variables de entorno.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logging.warning("⚠️ Variables de entorno TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configuradas. Omitiendo notificación.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            logging.error(f"❌ Error al enviar mensaje a Telegram: {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ Excepción al conectar con la API de Telegram: {e}")
        return False
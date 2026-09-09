import os
import requests
import logging
import time

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
    
    
    max_reintentos = 3
    espera_segundos = 2

    for intento in range(1, max_reintentos + 1):
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logging.info("📱 Notificación enviada a Telegram con éxito.")
            return  # Si la entrega es exitosa, sale de la función inmediatamente
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logging.warning(f"⚠️ Intento {intento}/{max_reintentos} falló por red/timeout: {e}")
            if intento < max_reintentos:
                time.sleep(espera_segundos)  # Espera antes de reintentar
            else:
                logging.error("❌ Se agotaron todos los reintentos para conectar con Telegram.")
                
        except requests.exceptions.RequestException as e:
            # Captura errores HTTP definitivos (ej. 400 Bad Request, 401 Unauthorized) sin reintentar inútilmente
            logging.error(f"⚠️ Error no recuperable al enviar a Telegram: {e}")
            break
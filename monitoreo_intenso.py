import requests
import time
from datetime import datetime
from plyer import notification

URL = "https://tioanime.com"
INTERVALO_SEGUNDOS = 60  # Espera entre reintentos

def esta_disponible(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True
        else:
            print(f"[{datetime.now()}] Estado: {response.status_code} - {response.reason}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Error al conectar: {e}")
        return False

def enviar_notificacion():
    notification.notify(
        title='¡TioAnime está disponible!',
        message='El sitio ya respondió correctamente.',
        timeout=10  # segundos
    )

def monitorear_sitio():
    print(f"Comenzando monitoreo de {URL}...\nPresiona Ctrl+C para detener.\n")
    while True:
        if esta_disponible(URL):
            print(f"[{datetime.now()}] 🟢 ¡TioAnime está disponible!")
            enviar_notificacion()
            break
        else:
            print(f"[{datetime.now()}] 🔴 TioAnime sigue caído. Reintentando en {INTERVALO_SEGUNDOS} segundos...\n")
            time.sleep(INTERVALO_SEGUNDOS)

if __name__ == "__main__":
    monitorear_sitio()

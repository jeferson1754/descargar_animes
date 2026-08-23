import os
import pickle
import json
import logging
import sys
import base64
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# --- CONFIGURACIÓN ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]

SPREADSHEET_ID = "1Z35OcOCf9tTHh9MVWvpAGnJrv8o7JShvwbokpLBFi7Y"

# Lista global para acumular los logs si deseas volcar logs a Sheets
logs_acumulados_sheets = []

class SheetsLogHandler(logging.Handler):
    """Handler personalizado para capturar logs y prepararlos para Google Sheets."""
    def emit(self, record):
        try:
            log_formateado = self.format(record)
            tiempo_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            logs_acumulados_sheets.append([tiempo_str, log_formateado])
        except Exception:
            self.handleError(record)

def configurar_logging():
    logger = logging.getLogger()
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.INFO)

    # 1. Terminal (Consola)
    formato_consola = logging.Formatter('%(levelname)-8s %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formato_consola)

    # 2. Archivo Local (Historial de texto plano)
    file_handler = logging.FileHandler('historial_ejecuciones.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s │ %(levelname)-8s │ %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

    # 3. Handler de Google Sheets
    sheets_handler = SheetsLogHandler()
    sheets_handler.setFormatter(formato_consola)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(sheets_handler)

    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# Inicializar logging
configurar_logging()


def obtener_conexion_google_sheets():
    """
    Autentica y devuelve el cliente de la API de Google Sheets.
    Compatible tanto para entorno local (token.pickle) como para GitHub Actions.
    """
    creds = None
    
    # 1. Intentar cargar desde token.pickle (Uso local habitual)
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)
            
    # 2. Si no hay token válido o expiró, intentamos refrescarlo o usar variables de entorno (para la nube)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.warning(f"⚠️ No se pudo refrescar el token automáticamente: {e}")
                creds = None

        if not creds:
            # Si estamos en GitHub Actions, puedes inyectar el token en formato base64 mediante un Secret
            token_base64 = os.environ.get("GOOGLE_TOKEN_PICKLE_B64")
            if token_base64:
                try:
                    creds_bytes = base64.b64decode(token_base64)
                    creds = pickle.loads(creds_bytes)
                    logging.info("🔐 Credenciales cargadas exitosamente desde variable de entorno (Base64).")
                except Exception as e:
                    logging.error(f"❌ Error al decodificar el token de GitHub Secrets: {e}")
            
    if not creds or not creds.valid:
        logging.error("❌ Error: No se encontró un token de Google Sheets válido. Ejecuta la autorización inicial en local.")
        return None

    try:
        # Construir y retornar el servicio de Google Sheets v4
        service = build("sheets", "v4", credentials=creds)
        return service
    except Exception as e:
        logging.error(f"❌ Error al conectar con la API de Google Sheets: {e}")
        return None


def guardar_resultados_en_sheets(sheet_service, resultados_animes):
    """
    Recibe la lista de animes encontrados con sus enlaces de descarga
    y los escribe directamente en tu Google Sheet.
    """
    if not sheet_service:
        logging.error("❌ No hay servicio de Sheets disponible para guardar los datos.")
        return False

    try:
        # Rango donde se insertarán los datos (ej. pestaña 'Pendientes!A:D')
        # Ajusta el nombre de la hoja según tu estructura en Google Sheets
        nombre_hoja = "Animes!A2" 
        
        filas_a_insertar = []
        for anime in resultados_animes:
            nombre = anime.get("nombre", "")
            nombre_anime = anime.get("nombre_anime", "")
            episodio = anime.get("episodio", "")
            link_descarga = anime.get("link_descarga", "")
            
            # Formato de la fila para tu Google Sheet
            filas_a_insertar.append([nombre_anime, episodio, link_descarga, "Pendiente"])

        body = {
            "values": filas_a_insertar
        }

        # Ejecutamos la petición para añadir filas al final o sobrescribir
        result = sheet_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_hoja,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        logging.info(f"✅ Se han guardado {len(filas_a_insertar)} registros en Google Sheets correctamente.")
        return True

    except Exception as e:
        logging.error(f"❌ Error al escribir en Google Sheets: {e}")
        return False
    
 
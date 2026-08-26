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
            tiempo_str = datetime.fromtimestamp(
                record.created).strftime("%Y-%m-%d %H:%M:%S")
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
    file_handler = logging.FileHandler(
        'historial_ejecuciones.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s │ %(levelname)-8s │ %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

    # 3. Handler de Google Sheets
    sheets_handler = SheetsLogHandler()
    sheets_handler.setFormatter(formato_consola)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(sheets_handler)

    logging.getLogger(
        'googleapiclient.discovery_cache').setLevel(logging.ERROR)


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
                logging.warning(
                    f"⚠️ No se pudo refrescar el token automáticamente: {e}")
                creds = None

        if not creds:
            # Si estamos en GitHub Actions, puedes inyectar el token en formato base64 mediante un Secret
            token_base64 = os.environ.get("GOOGLE_TOKEN_PICKLE_B64")
            if token_base64:
                try:
                    creds_bytes = base64.b64decode(token_base64)
                    creds = pickle.loads(creds_bytes)
                    logging.info(
                        "🔐 Credenciales cargadas exitosamente desde variable de entorno (Base64).")
                except Exception as e:
                    logging.error(
                        f"❌ Error al decodificar el token de GitHub Secrets: {e}")

    if not creds or not creds.valid:
        logging.error(
            "❌ Error: No se encontró un token de Google Sheets válido. Ejecuta la autorización inicial en local.")
        return None

    try:
        # Construir y retornar el servicio de Google Sheets v4
        service = build("sheets", "v4", credentials=creds)
        return service
    except Exception as e:
        logging.error(f"❌ Error al conectar con la API de Google Sheets: {e}")
        return None


def leer_animes_pendientes(sheet_service):
    """
    Lee dinámicamente los datos existentes en Google Sheets y devuelve 
    una lista con los animes ya registrados para evitar duplicados o búsquedas innecesarias.
    """
    if not sheet_service:
        print("❌ No hay conexión activa con Google Sheets.")
        return []

    try:
        rango_lectura = "Animes!A:D"

        # Solicitamos los datos a Google Sheets
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango_lectura
        ).execute()

        filas_totales_hoja = result.get("values", [])

        if not filas_totales_hoja:
            print("ℹ️ La hoja de cálculo está vacía.")
            return []

        # Omitimos la cabecera (fila 1)
        datos_existentes = filas_totales_hoja[1:]

        animes_registrados = []
        for fila in datos_existentes:
            # Aseguramos que la fila tenga al menos nombre y episodio
            if len(fila) >= 2:
                nombre = fila[0]
                episodio = fila[1]
                enlace = fila[2]
                estado = fila[3] if len(fila) > 3 else "Pendiente"

                animes_registrados.append({
                    "nombre": nombre,
                    "episodio": episodio,
                    "enlace": enlace,
                    "estado": estado
                })

        print(
            f"📖 Se leyeron {len(animes_registrados)} registros previos desde Google Sheets.")
        return animes_registrados

    except Exception as e:
        print(f"❌ Error al leer los animes desde Google Sheets: {e}")
        return []


def guardar_y_actualizar_historial_sheets(sheet_service, resultados_animes):
    """
    Lee dinámicamente los datos existentes, coloca lo nuevo arriba, 
    marca lo viejo como 'Completado' y actualiza la hoja sin rangos fijos.
    """
    if not sheet_service:
        print("❌ No hay conexión activa con Google Sheets.")
        return False

    try:
        # 1. Rango dinámico: Solicitamos toda la columna A:D con datos
        rango_lectura = "Animes!A:D"

        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango_lectura
        ).execute()

        filas_totales_hoja = result.get("values", [])

        filas_antiguas = []
        if filas_totales_hoja:
            # Separamos la cabecera (fila 1) del resto del contenido (filas 2 en adelante)
            datos_existentes = filas_totales_hoja[1:]

            # 2. Transformamos las filas antiguas: las marcamos como "Completado"
            for fila in datos_existentes:
                # Aseguramos que la fila tenga las 4 columnas cubiertas
                while len(fila) < 4:
                    fila.append("Pendiente")

                # Si estaba pendiente, lo pasamos a completado
                if fila[3].lower() == "pendiente":
                    fila[3] = "Completado"

                filas_antiguas.append(fila)

        # 3. Preparamos los nuevos resultados con su estado correspondiente
        filas_nuevas = []
        for anime in resultados_animes:
            nombre_anime = anime.get("nombre_anime") or anime.get("nombre", "")
            episodio = anime.get("episodio", "") or anime.get(
                "episodio_buscado", "")
            link_descarga = anime.get("link_descarga", "")
            estado = anime.get("estado", "Pendiente")

            filas_nuevas.append(
                [nombre_anime, str(episodio), link_descarga, estado])

        if not filas_nuevas:
            print("ℹ️ No hay registros nuevos para actualizar en Google Sheets.")
            return False

        # 4. Combinamos: Lo nuevo arriba, lo viejo abajo
        nuevos_datos_combinados = filas_nuevas + filas_antiguas

        # Agregamos de nuevo la cabecera al principio de todo el bloque
        filas_finales = [["Anime", "Episodio", "Enlace",
                          "Estado"]] + nuevos_datos_combinados

        # 5. Limpiamos toda la hoja de forma limpia (sin importar cuántas filas tenía)
        sheet_service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range="Animes!A:D",
            body={}
        ).execute()

        # 6. Escribimos todo el bloque optimizado desde la celda A1
        body = {
            "values": filas_finales
        }

        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range="Animes!A1",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        print(
            f"✅ Google Sheets sincronizado dinámicamente: {len(filas_nuevas)} registros nuevos arriba.")
        return True

    except Exception as e:
        print(f"❌ Error al actualizar el historial en Google Sheets: {e}")
        return False


def actualizar_estado_google_sheets(sheet_service, nombre_hoja, nombre_anime, episodio, nuevo_estado="Completado"):
    """
    Busca un anime y episodio específico usando la API oficial de Google Sheets
    y actualiza su columna de estado en la hoja correspondiente.
    """
    try:
        # 1. Leemos todo el contenido de la hoja para encontrar la fila exacta
        rango_lectura = f"{nombre_hoja}!A:D"
        resultado_lectura = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango_lectura
        ).execute()
        
        filas = resultado_lectura.get('values', [])
        
        if not filas:
            print("❌ La hoja de Google Sheets está vacía.")
            return False
        
        # Definimos las posiciones fijas de tus columnas
        col_nombre_idx = 0  # Columna A (Anime)
        col_ep_idx = 1      # Columna B (Episodio)
        col_estado_idx = 3  # Columna D (Estado)

        # La primera fila contiene los encabezados
        encabezados = [h.lower() for h in filas[0]]
        


       # 2. Buscar la fila que coincide con el anime y el episodio (saltando la cabecera en fila 1)
        fila_encontrada_num = None
        for index, fila in enumerate(filas[1:], start=2):
            # Nos aseguramos de que la fila tenga suficientes columnas para leer
            if len(fila) > max(col_nombre_idx, col_ep_idx):
                val_nombre = str(fila[col_nombre_idx]).strip().lower()
                val_ep = str(fila[col_ep_idx]).strip()
                
                if val_nombre == str(nombre_anime).strip().lower() and val_ep == str(episodio).strip():
                    fila_encontrada_num = index
                    break

        if not fila_encontrada_num:
            print(f"⚠️ No se encontró '{nombre_anime}' Ep. {episodio} en Google Sheets para actualizar.")
            return False

      # 3. Construir la notación de celda exacta para la Columna D (Estado)
        # La columna D es el índice 3, por lo que corresponde a la letra 'D'
        celda_destino = f"{nombre_hoja}!D{fila_encontrada_num}"

        # 4. Actualizar el valor en la celda
        body = {
            "values": [[nuevo_estado]]
        }
        
        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=celda_destino,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        print(f"✅ Google Sheets actualizado: '{nombre_anime}' (Ep. {episodio}) -> '{nuevo_estado}'")
        return True

    except Exception as e:
        print(f"❌ Error al actualizar Google Sheets: {e}")
        return False
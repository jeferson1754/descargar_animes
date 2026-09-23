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
from notificaciones_telegram import enviar_mensaje_telegram

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
    únicamente la lista de animes con estado 'Pendiente' o 'Cambiar Fuente'.
    """
    if not sheet_service:
        logging.error("❌ No hay conexión activa con Google Sheets.")
        return []

    try:
        rango_lectura = "Animes!A:I"

        # Solicitamos los datos a Google Sheets
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango_lectura
        ).execute()

        filas_totales_hoja = result.get("values", [])

        if not filas_totales_hoja:
            logging.info("ℹ️ La hoja de cálculo está vacía.")
            return []

        # Omitimos la cabecera (fila 1)
        datos_existentes = filas_totales_hoja[1:]

        animes_registrados = []

        for fila in datos_existentes:
            if len(fila) >= 2:
                nombre = fila[0].strip()
                episodio = fila[1].strip()
                enlace = fila[2].strip() if len(fila) > 2 else ""
                fuente = fila[3].strip() if len(fila) > 3 else ""
                fuente_fallida = fila[4].strip() if len(fila) > 4 else ""
                fecha_deteccion = fila[5].strip() if len(fila) > 5 else ""
                fecha_actualizacion = fila[6].strip() if len(fila) > 6 else ""
                fecha_descarga = fila[7].strip() if len(fila) > 7 else ""
                estado = fila[8].strip() if len(fila) > 8 else "Pendiente"

                # Filtrar solo si el estado es 'Pendiente' o 'Cambiar Fuente'

                animes_registrados.append({
                    "nombre": nombre,
                    "episodio": episodio,
                    "enlace": enlace,
                    "fuente": fuente,
                    "fuente_fallida": fuente_fallida,
                    "fecha_deteccion": fecha_deteccion,
                    "fecha_actualizacion": fecha_actualizacion,
                    "fecha_descarga": fecha_descarga,
                    "estado": estado
                })

        logging.info(
            f"📖 Se leyeron {len(animes_registrados)} registros activos desde Google Sheets."
        )
        return animes_registrados

    except Exception as e:
        logging.error(f"❌ Error al leer los animes desde Google Sheets: {e}")
        return []


def guardar_y_actualizar_historial_sheets(sheet_service, resultados_animes):
    """
    Lee los datos existentes, elimina duplicados previos de los registros nuevos,
    los ubica al inicio, actualiza Google Sheets y notifica por Telegram.
    """
    if not sheet_service:
        logging.error("❌ No hay conexión activa con Google Sheets.")
        return False

    try:
        rango_lectura = "Animes!A:I"
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango_lectura
        ).execute()

        filas_totales_hoja = result.get("values", [])

        filas_antiguas = []
        if filas_totales_hoja:
            datos_existentes = filas_totales_hoja[1:]
            for fila in datos_existentes:
                while len(fila) < 9:
                    fila.append("")
                filas_antiguas.append(fila)

        tiempo_actual = datetime.now().strftime("%Y-%m-%d %H:%M")

        filas_nuevas = []
        claves_nuevas = set()

        for anime in resultados_animes:
            nombre_anime = anime.get("nombre_anime") or anime.get("nombre", "")
            episodio = anime.get("episodio", "") or anime.get(
                "episodio_buscado", "")
            link_descarga = anime.get("link_descarga", "")
            fuente = anime.get("fuente", "TioAnime")
            fuente_fallida = anime.get("fuente_fallida", "")

            f_deteccion = anime.get("fecha_deteccion") or tiempo_actual
            f_actualizacion = anime.get("fecha_actualizacion", "")
            f_descarga = anime.get("fecha_descarga", "")
            estado = anime.get("estado", "Pendiente")

            filas_nuevas.append([
                nombre_anime,
                str(episodio),
                link_descarga,
                fuente,
                fuente_fallida,
                f_deteccion,
                f_actualizacion,
                f_descarga,
                estado
            ])
            # Clave única para identificar duplicados: (nombre_lowercase, episodio_string)
            claves_nuevas.add(
                (str(nombre_anime).strip().lower(), str(episodio).strip()))

        if not filas_nuevas:
            logging.info(
                "ℹ️ No hay registros nuevos para actualizar en Google Sheets.")
            return False

        # 🛠️ FIX 1: Filtrar filas antiguas para eliminar versiones previas de las que se están insertando
        filas_antiguas_filtradas = []
        for fila in filas_antiguas:
            clave_antigua = (
                str(fila[0]).strip().lower(), str(fila[1]).strip())
            if clave_antigua not in claves_nuevas:
                filas_antiguas_filtradas.append(fila)

        # Combinar: Lo nuevo arriba, lo antiguo sin duplicados abajo
        nuevos_datos_combinados = filas_nuevas + filas_antiguas_filtradas

        filas_finales = [[
            "Anime", "Episodio", "Enlace", "Fuente",
            "Fuentes Fallidas", "Fecha Detección",
            "Fecha Actualización", "Fecha Descarga", "Estado"
        ]] + nuevos_datos_combinados

        # Limpiar y escribir
        sheet_service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range="Animes!A:I",
            body={}
        ).execute()

        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range="Animes!A1",
            valueInputOption="USER_ENTERED",
            body={"values": filas_finales}
        ).execute()

        logging.info(
            f"✅ Google Sheets sincronizado: {len(filas_nuevas)} registros nuevos insertados arriba.")

        # 📋 FIX 2: Construir lista de pendientes sin duplicados
        lista_pendientes = []
        for anime in resultados_animes:
            nombre = anime.get("nombre_anime") or anime.get(
                "nombre", "Desconocido")
            episodio = anime.get("episodio", "") or anime.get(
                "episodio_buscado", "")
            if str(anime.get("estado", "Pendiente")).lower() == "pendiente":
                lista_pendientes.append(
                    f"• *{nombre}* (Ep. {episodio}) _[Nuevo]_")

        for fila in filas_antiguas_filtradas:
            if str(fila[8]).strip().lower() == "pendiente":
                lista_pendientes.append(f"• *{fila[0]}* (Ep. {fila[1]})")

        cadena_pendientes = "\n".join(
            lista_pendientes) if lista_pendientes else "Ninguno"

        mensaje = (
            f"🤖 *Bot de Animes*\n\n"
            f"✅ Búsqueda finalizada.\n"
            f"🆕 Nuevos registrados: *{len(filas_nuevas)}*\n"
            f"📌 Total de episodios pendientes: *{len(lista_pendientes)}*\n\n"
            f"📋 *Lista de Pendientes:*\n"
            f"{cadena_pendientes}"
        )

        enviar_mensaje_telegram(mensaje)
        return True

    except Exception as e:
        logging.error(
            f"❌ Error al actualizar el historial en Google Sheets: {e}")
        return False


def actualizar_estado_google_sheets(
    sheet_service,
    nombre_hoja,
    nombre_anime,
    episodio,
    nuevo_estado="Completado",
    nuevo_enlace=None,
    nueva_fuente=None,
    fuentes_fallidas=None,
    fecha_actualizacion=None,
    crear_si_no_existe=True
):
    """
    Busca y actualiza un registro existente. Si no existe y crear_si_no_existe=True,
    crea la fila al final de la hoja de forma segura.
    """
    if not sheet_service:
        logging.error("❌ No hay conexión activa con Google Sheets.")
        return False

    try:
        rango_lectura = f"{nombre_hoja}!A:I"
        resultado_lectura = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango_lectura
        ).execute()

        filas = resultado_lectura.get('values', [])
        tiempo_actual = datetime.now().strftime("%Y-%m-%d %H:%M")

        col_nombre_idx = 0
        col_ep_idx = 1
        fila_encontrada_num = None
        fila_actual = []

        if filas:
            for index, fila in enumerate(filas[1:], start=2):
                if len(fila) > max(col_nombre_idx, col_ep_idx):
                    val_nombre = str(fila[col_nombre_idx]).strip().lower()
                    val_ep = str(fila[col_ep_idx]).strip()

                    if val_nombre == str(nombre_anime).strip().lower() and val_ep == str(episodio).strip():
                        fila_encontrada_num = index
                        fila_actual = list(fila)
                        break

        # Si no existe la fila, la agregamos al final
        if not fila_encontrada_num:
            if crear_si_no_existe:
                # 🟢 CAMBIO 1: Solo usa fecha_actualizacion si viene como string, si no, queda vacío ("")
                f_act = fecha_actualizacion if isinstance(
                    fecha_actualizacion, str) else ""
                f_desc = tiempo_actual if nuevo_estado == "Completado" else ""

                nueva_fila = [
                    nombre_anime,
                    str(episodio),
                    str(nuevo_enlace or ""),
                    str(nueva_fuente or ""),
                    str(fuentes_fallidas or ""),
                    tiempo_actual,  # Fecha Detección
                    # Fecha Actualización (queda vacío si no se especifica)
                    f_act,
                    f_desc,         # Fecha Descarga
                    str(nuevo_estado)
                ]

                sheet_service.spreadsheets().values().append(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{nombre_hoja}!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [nueva_fila]}
                ).execute()

                logging.info(
                    f"➕ Registro creado al final de Sheets: '{nombre_anime}' (Ep. {episodio}) -> Estado: '{nuevo_estado}'")
                return True
            else:
                logging.error(
                    f"⚠️ No se encontró '{nombre_anime}' Ep. {episodio} en Google Sheets para actualizar.")
                return False

        # Normalizar a 9 columnas si la fila ya existía
        while len(fila_actual) < 9:
            fila_actual.append("")

        # Actualizar campos de enlace y fuentes solo si se pasaron
        if nuevo_enlace is not None:
            fila_actual[2] = str(nuevo_enlace)
        if nueva_fuente is not None:
            fila_actual[3] = str(nueva_fuente)
        if fuentes_fallidas is not None:
            fila_actual[4] = str(fuentes_fallidas)

        # 🟢 CAMBIO 2: Solo actualiza Fecha Actualización (índice 6) si se pasa explícitamente.
        # Si fecha_actualizacion es None, se MANTIENE intacto lo que ya había en el Sheet.
        if fecha_actualizacion is not None:
            fila_actual[6] = str(fecha_actualizacion)

        # Si el estado pasa a Completado, grabamos la fecha de descarga
        if nuevo_estado == "Completado":
            fila_actual[7] = tiempo_actual

        fila_actual[8] = str(nuevo_estado)

        celda_destino = f"{nombre_hoja}!A{fila_encontrada_num}:I{fila_encontrada_num}"

        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=celda_destino,
            valueInputOption="USER_ENTERED",
            body={"values": [fila_actual]}
        ).execute()

        logging.info(
            f"✅ Google Sheets actualizado: '{nombre_anime}' (Ep. {episodio}) -> Estado: '{nuevo_estado}'")
        return True

    except Exception as e:
        logging.error(f"❌ Error al actualizar Google Sheets: {e}")
        return False


def verificar_animes_desaparecidos(sheet_service, animes_registrados_sheets, animes_encontrados_web):
    """
    Compara los animes pendientes en Google Sheets con los encontrados en la web.
    Si un anime pendiente ya no está en la web, actualiza su estado a 'Completado'.
    """
    if not sheet_service:
        return

# Normalizamos correctamente los datos que vienen de la web
    animes_web_set = set()
    for a in animes_encontrados_web:
        nombre = str(a.get("nombre_anime", a.get("nombre", ""))
                     ).strip().lower()
        episodio = str(a.get("episodio", a.get(
            "episodio_buscado", ""))).strip()
        if nombre and episodio:
            animes_web_set.add((nombre, episodio))

    logging.info(
        "🔍 Verificando animes pendientes frente al servidor actual...")

    actualizaciones_realizadas = 0

    for item in animes_registrados_sheets:
        # Solo evaluamos registros que estén estrictamente como "Pendiente"
        if item.get("estado", "").strip().lower() == "pendiente":
            nombre_sheet = str(item.get("nombre", "")).strip().lower()
            episodio_sheet = str(item.get("episodio", "")).strip()

            # Si el anime y episodio que estaban pendientes YA NO figuran en la web actual
            if (nombre_sheet, episodio_sheet) not in animes_web_set:
                logging.info(
                    f"🔄 '{item.get('nombre')}' Ep. {episodio_sheet} ya no está en la web. Cambiando a 'Completado'...")

                exito = actualizar_estado_google_sheets(
                    sheet_service,
                    nombre_hoja="Animes",
                    nombre_anime=item.get("nombre"),
                    episodio=episodio_sheet,
                    nuevo_estado="Completado"
                )

                if exito:
                    actualizaciones_realizadas += 1

    if actualizaciones_realizadas > 0:
        logging.info(
            f"✅ Se actualizaron {actualizaciones_realizadas} animes a 'Completado'.")
    else:
        logging.info(
            "ℹ️ Todos los animes pendientes siguen vigentes en el servidor.")


def guardar_logs_en_sheets(service):
    """Envía los logs a la pestaña Historial, insertándolos ARRIBA (Fila 2)."""
    global logs_acumulados_sheets

    if not logs_acumulados_sheets:
        return

    nombre_hoja_historial = "Historial"

    try:
        # 1. Preparamos el bloque de logs
        logs_a_subir = [
            ["", "──────────────────────────────────────────────────"]] + logs_acumulados_sheets
        cantidad_filas = len(logs_a_subir)

        # 2. Obtenemos el sheetId interno de la pestaña "Historial"
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=SPREADSHEET_ID).execute()
        sheet_id = None
        for sheet in sheet_metadata.get('sheets', []):
            if sheet['properties']['title'] == nombre_hoja_historial:
                sheet_id = sheet['properties']['sheetId']
                break

        if sheet_id is None:
            logging.error(
                f"⚠️ No se encontró la pestaña {nombre_hoja_historial}.")
            return

        # 3. Insertamos filas en blanco EXACTAMENTE debajo de la cabecera (Fila 2 / startIndex: 1)
        # Esto empuja todo el historial viejo hacia abajo sin borrar nada
        requests = [{
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 1,  # Índice 1 = Fila 2 en Sheets
                    "endIndex": 1 + cantidad_filas
                },
                "inheritFromBefore": False
            }
        }]
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": requests}
        ).execute()

        # 4. Escribimos los logs nuevos en ese hueco que acabamos de crear (desde A2)
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{nombre_hoja_historial}!A2",
            valueInputOption="USER_ENTERED",
            body={"values": logs_a_subir}
        ).execute()

        logging.info(
            "📊 ¡Historial actualizado en la parte SUPERIOR de la hoja!")

        # Limpiamos la lista para la próxima vez
        logs_acumulados_sheets.clear()

    except Exception as e:
        logging.error(f"⚠️ No se pudieron subir los logs a Sheets: {e}")

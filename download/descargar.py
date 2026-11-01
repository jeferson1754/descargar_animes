import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from urllib.parse import urlparse
import os
import logging
import html
import re
import json

from utilidades.archivos import leer_nombres_desde_txt, guardar_resultados_videos_txt
from utilidades.navegador import configurar_navegador
from utilidades.limpieza import obtener_directorio_fecha
from animes.buscador import buscar_en_fuentes
from config import FUENTES_ANIME, SERVIDOR
from base_excel import obtener_conexion_google_sheets, guardar_y_actualizar_historial_sheets, leer_animes_pendientes, actualizar_estado_google_sheets, guardar_logs_en_sheets
from notificaciones_telegram import enviar_mensaje_telegram
from animes.comparador import tomar_captura_express
from animes.coincidencia import validar_coincidencia_anime, normalizar_texto


# ==========================================
# CONFIGURACIÓN DE LAS NUEVAS VALIDACIONES
# ==========================================

# Máximo de veces que se cambia de servidor/fuente para UN mismo episodio
# durante la fase de descarga local antes de rendirse.
MAX_CAMBIOS_FUENTE = 5

# Archivo donde se guardan los servidores alternos ya validados de cada
# episodio (la fase "nube" los escribe y la fase "local" los lee).
ARCHIVO_SERVIDORES_ALTERNOS = "servidores_alternos.json"

# (La configuración de la validación de coincidencia -ALIAS_ANIME, umbrales,
#  etc.- está ahora en animes/coincidencia.py)

NOMBRES_SERVIDOR_LEGIBLES = {
    "mega": "Mega",
    "voe": "VOE",
    "mixdrop": "Mixdrop",
    "mp4upload": "Mp4Upload",
    "mediafire": "MediaFire",
    "gofile": "Gofile",
    "streamtape": "Streamtape",
    "doodstream": "Doodstream",
}


def verificar_descarga(
    download_dir,
    archivos_antes,
    tiempo_maximo=1800,
    intervalo=2,
    tiempo_estable=6
):
    """
    Espera hasta que aparezca una descarga terminada.

    - Detecta archivos temporales de Chrome (.crdownload)
    - Espera hasta que desaparezcan
    - Comprueba que exista un archivo final
    - Comprueba que su tamaño deje de cambiar
    - Devuelve la ruta del archivo terminado
    """

    inicio = time.time()
    archivo_anterior = None
    tamano_anterior = -1
    segundos_estable = 0

    extensiones_video = (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv"
    )

    extensiones_temporales = (
        ".crdownload",
        ".part",
        ".tmp"
    )

    logging.info("Esperando a que termine la descarga...")

    while time.time() - inicio < tiempo_maximo:

        try:
            archivos_actuales = set(os.listdir(download_dir))
        except OSError as e:
            logging.error(f"❌ No se pudo leer la carpeta de descargas: {e}")
            time.sleep(intervalo)
            continue

        temporales = [
            archivo
            for archivo in archivos_actuales
            if archivo.lower().endswith(
                extensiones_temporales
            )
        ]

        if temporales:
            logging.info(
                f"⬇️ Descarga en progreso... "
                f"({len(temporales)} archivo(s) temporal(es))"
            )

            segundos_estable = 0
            time.sleep(intervalo)
            continue

        # --------------------------------------------------
        # 2. Buscar archivos de video NUEVOS
        # --------------------------------------------------

        archivos_nuevos = (
            archivos_actuales - archivos_antes
        )

        videos_nuevos = [
            archivo
            for archivo in archivos_nuevos
            if archivo.lower().endswith(extensiones_video)
        ]

        if videos_nuevos:

            # El más recientemente modificado
            archivo = max(
                videos_nuevos,
                key=lambda x: os.path.getmtime(
                    os.path.join(download_dir, x)
                )
            )

            ruta = os.path.join(download_dir, archivo)

            try:
                tamano_actual = os.path.getsize(ruta)
            except OSError:
                time.sleep(intervalo)
                continue

            # --------------------------------------------------
            # 3. Comprobar que el archivo deje de crecer
            # --------------------------------------------------

            if archivo == archivo_anterior:

                if tamano_actual == tamano_anterior:
                    segundos_estable += intervalo
                else:
                    segundos_estable = 0

            else:
                archivo_anterior = archivo
                segundos_estable = 0

            tamano_anterior = tamano_actual

            logging.info(
                f"📦 Archivo detectado: {archivo} | "
                f"{tamano_actual / (1024 * 1024):.2f} MB | "
                f"estable: {segundos_estable}s"
            )

            # --------------------------------------------------
            # 4. Confirmación real
            # --------------------------------------------------

            if (
                tamano_actual > 0
                and segundos_estable >= tiempo_estable
            ):
                logging.info(
                    f"✅ Descarga confirmada: {archivo}"
                )

                return ruta

        time.sleep(intervalo)

    # ------------------------------------------------------
    # 5. Timeout
    # ------------------------------------------------------

    minutos = tiempo_maximo // 60

    logging.error(
        f"❌ Timeout: la descarga no terminó "
        f"después de {minutos} minutos."
    )

    return None


def marcar_anime_descargado_con_selenium(driver, nombre_anime, episodio):
    """
    Navega a la URL del servidor web con Selenium para marcar el anime como descargado.
    """
    try:
        # Construye la URL de actualización con los parámetros necesarios (ajusta según tu PHP)
        url_servidor = f"{SERVIDOR}/Anime/Emision/actualizar.php?nombre_anime={nombre_anime}&episodio={episodio}"
        logging.info(
            f"🌐 Actualizando servidor mediante Selenium: {nombre_anime} - Ep {episodio} / {url_servidor}")

        # El navegador entra a la página de actualización
        driver.get(url_servidor)

        # Opcional: Pequeña pausa para asegurar que el servidor procese la petición en la base de datos
        time.sleep(2)

        logging.info(f"✅ Servidor actualizado exitosamente.")

        return True

    except Exception as e:
        logging.error(f"⚠️ Error al actualizar el servidor con Selenium: {e}")
        return False


def buscar_enlace_descarga_y_actualizar(driver, videos_encontrados):
    """Busca el enlace de descarga (Mega) para cada video y lo agrega a la lista."""

    videos_con_descarga = []

    for video in videos_encontrados:

        # Reutilizamos la lógica de buscar_boton_descarga pero sin hacer clic aún
        enlace_descarga = buscar_boton_descarga(driver, video['enlace'])

        if enlace_descarga:
            video['link_descarga'] = enlace_descarga
        else:
            video['link_descarga'] = "No encontrado"

        videos_con_descarga.append(video)

    return videos_con_descarga


def buscar_boton_descarga(driver, video_url):

    if driver is None:
        logging.error(
            "❌ No hay driver disponible."
        )
        return None

    try:
        driver.get(video_url)
        time.sleep(5)  # Espera para que la página cargue

        # Buscar el botón de descarga
        boton_descarga = driver.find_element(By.CLASS_NAME, "btn-success")
        if boton_descarga:
            # Obtener el enlace de descarga
            enlace_descarga = boton_descarga.get_attribute("href")
            return enlace_descarga
        else:
            logging.info(f"No se encontró el botón de descarga en {video_url}")
            return None

    except Exception as e:
        logging.error(f"Error al acceder a {video_url}: {e}")
        return None



DOMINIOS_VOE = (
    "voe.sx", "voe-un-block", "johnfullwonder", "jamesbornmain",
    "teresapoliticallearn", "shannoncoldalready",
)

# Dominios de publicidad/redirectores conocidos (ajusta a tu caso)
DOMINIOS_PUBLICIDAD = ("doubleclick", "popads", "adsterra", "propellerads")

# Ruta raíz tipo /bs0jzeblyjhm (id alfanumérico de 10-16 chars)
RE_ID_RAIZ = re.compile(r"^/[a-z0-9]{10,16}/?$", re.I)
# Rutas clásicas /e/<id>, /v/<id>, /d/<id>
RE_ID_PREFIJO = re.compile(r"^/(?:e|v|d)/[a-z0-9]{10,16}/?$", re.I)

FIRMAS_HTML = (
    "voe.sx", "voe-network", "voe player", "vplayer",
    "delivery_node", "node_id", "voe-player",
)


def es_servidor_voe(driver, url, umbral=3):
    """Detecta VOE por puntuación: estructura de URL + contenido + DOM."""
    url = (url or "").strip()
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    # Descartar publicidad conocida de entrada
    if any(ad in host for ad in DOMINIOS_PUBLICIDAD):
        return False

    # Dominio conocido: confirmación inmediata
    if any(d in host for d in DOMINIOS_VOE):
        return True

    puntos = 0

    # 1. Estructura de URL
    if RE_ID_PREFIJO.match(path):
        puntos += 2
    elif RE_ID_RAIZ.match(path):
        puntos += 2  # dominio rotativo con id en la raíz

    # Sin driver real, solo podemos juzgar por la URL
    if isinstance(driver, str):
        return puntos >= 2 and bool(RE_ID_PREFIJO.match(path))

    # 2. Contenido de la página
    try:
        source = (driver.page_source or "").lower()
        title = (driver.title or "").lower()
    except Exception:
        return puntos >= umbral

    if "voe" in title:
        puntos += 2

    coincidencias = sum(1 for f in FIRMAS_HTML if f in source)
    puntos += min(coincidencias, 3)

    # 3. Elementos típicos del reproductor/descarga
    try:
        from selenium.webdriver.common.by import By
        if driver.find_elements(By.CSS_SELECTOR, "video, #voe-player, .plyr, .video-js"):
            puntos += 1
        if driver.find_elements(By.XPATH,
                "//a[contains(translate(., 'DOWNLOAD', 'download'), 'download')]"
                " | //button[contains(translate(., 'DOWNLOAD', 'download'), 'download')]"):
            puntos += 1
    except Exception:
        pass

    return puntos >= umbral

def detectar_servidor_descarga(driver):
    """Detecta el servidor analizando la URL, los atributos href,

    el texto visible y el código fuente en páginas intermedias.
    """
    if isinstance(driver, str):
        url = driver.lower()
    else:
        url = driver.current_url.lower()

    time.sleep(2)

    # --------------------------------------------------
    # 1. Detección rápida por URL / Patrones
    # --------------------------------------------------
    if "mega.nz" in url or "mega.co.nz" in url:
        return "mega"

    # Detección inteligente de VOE
    if es_servidor_voe(driver, url):
        return "voe"

    if "mixdrop" in url or "miixdrop" in url or "mxdrop.top" in url:
        return "mixdrop"
    if "mp4upload.com" in url:
        return "mp4upload"
    if "mediafire.com" in url:
        return "mediafire"
    if "gofile.io" in url:
        return "gofile"

    # --------------------------------------------------
    # 2. Búsqueda profunda en elementos de la página
    # --------------------------------------------------
    if not isinstance(driver, str):
        try:
            elementos = driver.find_elements(
                By.TAG_NAME, "a"
            ) + driver.find_elements(By.TAG_NAME, "button")

            for elemento in elementos:
                try:
                    href = elemento.get_attribute("href") or ""
                    texto = elemento.text.lower()
                    contenido_total = f"{href} {texto}".lower()

                    if "mega" in contenido_total:
                        return "mega"
                    if es_servidor_voe(href, href) or "voe" in contenido_total:
                        return "voe"
                    if "mixdrop" in contenido_total:
                        return "mixdrop"
                    if "mp4upload" in contenido_total:
                        return "mp4upload"
                    if "mediafire" in contenido_total:
                        return "mediafire"
                    if "gofile" in contenido_total:
                        return "gofile"
                except Exception:
                    continue

        except Exception as e:
            logging.error(
                f"⚠️ Error detectando servidor en página intermedia: {e}"
            )

    return "desconocido"


def nombre_servidor_desde_url(url):
    """
    Versión ligera (sin sleep ni navegador) de detectar_servidor_descarga:
    identifica el servidor de descarga únicamente a partir del texto de la URL.
    Devuelve: 'mega', 'mixdrop', 'mp4upload', 'mediafire', 'gofile',
    'streamtape', 'doodstream', 'voe' o 'desconocido'.
    """
    url = (url or "").lower()

    if "mega.nz" in url or "mega.co.nz" in url:
        return "mega"
    if "mixdrop" in url or "miixdrop" in url or "mxdrop" in url:
        return "mixdrop"
    if "mp4upload.com" in url:
        return "mp4upload"
    if "mediafire.com" in url:
        return "mediafire"
    if "gofile.io" in url:
        return "gofile"
    if "streamtape" in url:
        return "streamtape"
    if "dood" in url:
        return "doodstream"
    # VOE va al final porque su detección por palabra clave es muy amplia
    if es_servidor_voe(url, url):
        return "voe"

    return "desconocido"


def nombre_servidor_legible(servidor=None, enlace=None):
    """Devuelve un nombre bonito para mostrar en Telegram (Mega, VOE, ...)."""
    clave = (servidor or "").strip().lower()

    if clave not in NOMBRES_SERVIDOR_LEGIBLES:
        deducido = nombre_servidor_desde_url(enlace)
        if deducido != "desconocido":
            clave = deducido

    if clave in NOMBRES_SERVIDOR_LEGIBLES:
        return NOMBRES_SERVIDOR_LEGIBLES[clave]

    return (servidor or "").strip() or "Desconocido"


def encontrar_boton_descarga(driver, servidor):
    """
    Busca el botón de descarga dependiendo del servidor.
    """

    selectores = {
        "mega": [
            # 1. Por atributo de ayuda/tooltip (El más preciso y estable)
            (By.CSS_SELECTOR, "button[data-simpletip='Descargar']"),
            (By.CSS_SELECTOR, "button[data-simpletip='Download']"),

            # 2. Por XPATH buscando el ícono de descarga interno o el atributo simpletip
            (By.XPATH,
             "//button[contains(@class, 'mega-component') and contains(@data-simpletip, 'Descargar')]"),
            (By.XPATH,
             "//button[contains(@class, 'mega-component') and .//i[contains(@class, 'icon-arrow-down')]]"),

            # 3. Selector amplio de clase para cualquier variante del botón de descarga principal
            (By.CSS_SELECTOR, "button.mega-component.secondary.button"),

            # 4. Fallbacks anteriores (por si carga la versión web de escritorio amplia)
            (By.CSS_SELECTOR, ".mega-component.lg-size.secondary.icon-loading.visible-txt.nav-elem.normal.button"),
        ],

        "streamtape": [
            (By.CSS_SELECTOR, "#download"),
        ],
        "mediafire": [
            (By.CSS_SELECTOR, "#downloadButton"),
            (By.CSS_SELECTOR, "a.popservers"),
            (By.CSS_SELECTOR, "a[aria-label*='Download file']")
        ],
        "voe": [
            (By.CSS_SELECTOR, "a.download-user-file"),
            (By.CSS_SELECTOR, "a[href*='download']"),
            (By.XPATH, "//a[contains(text(), 'Descargar ahora')]"),
        ],
        "mixdrop": [
            (By.CSS_SELECTOR, "a.download-btn"),
            (By.CSS_SELECTOR, "a[href*='download']"),
        ],
        "mp4upload": [
            (By.ID, "method_free"),
            (By.CSS_SELECTOR, "input#method_free:not([disabled])"),
            (By.CSS_SELECTOR, "input.downloadbtn"),
        ],
        "doodstream": [
            (By.CSS_SELECTOR, "a.download_vd"),
            (By.CSS_SELECTOR, "a[href='#download_now']"),
        ],
        "gofile": [
            (By.CSS_SELECTOR, "button[data-action='download']"),
            (By.CSS_SELECTOR, "button[title='Download']"),
        ]
    }

    if servidor not in selectores:
        logging.error(f"⚠️ Botón no encontrado o reconocido: {servidor}")
        return None

    for tipo_selector, selector in selectores[servidor]:
        try:
            boton = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((tipo_selector, selector))
            )

            logging.info(f"🖱️ Botón encontrado para servidor: {servidor}")
            return boton

        except Exception:
            continue

    logging.error(f"❌ No se encontró botón para servidor: {servidor}")
    return None


def asegurar_permanencia_en_servidor(driver, enlace_descarga, servidor_esperado):
    """Verifica si el navegador fue redirigido a un sitio publicitario

    y fuerza el regreso al enlace original de descarga.
    """
    time.sleep(4)  # Tiempo de espera para detectar si salta la redirección

    url_actual = driver.current_url.lower()

    # Dominios o patrones de sitios publicitarios conocidos
    dominios_basura = [
        "signaldefendgo",
        "bdsclk",
        "pets/rabbits",
        "clickid=",
        "track",
    ]

    # Si la URL actual no contiene el servidor esperado o contiene un patrón de anuncio
    es_basura = any(basura in url_actual for basura in dominios_basura)
    es_servidor_correcto = servidor_esperado in url_actual

    if es_basura or not es_servidor_correcto:
        logging.warning(
            f"⚠️ Redirección publicitaria detectada ({url_actual[:40]}...). Recargando enlace original..."
        )
        driver.get(enlace_descarga)
        time.sleep(3)


def hacer_click_en_boton_descarga(
    driver, enlace_descarga, download_dir, nombre_video, fuente
):
    """Inicia una descarga y espera hasta confirmar

    que apareció un archivo nuevo y terminó de crecer.

    Devuelve:
        True            -> descarga confirmada
        False           -> descarga fallida
        "archivo_caido" -> el enlace ya no existe o fue eliminado
        "cuota_agotada" -> límite de transferencia alcanzado (Mega)
    """
    def cerrar_pestañas_publicitarias(driver, ventana_principal):
        """Cierra cualquier pestaña/ventana emergente (pop-up) que no sea la principal."""
        try:
            time.sleep(1)
            pestañas_actuales = driver.window_handles
            if len(pestañas_actuales) > 1:
                for handle in pestañas_actuales:
                    if handle != ventana_principal:
                        driver.switch_to.window(handle)
                        driver.close()
                        logging.info("🧹 Pop-up/Anuncio cerrado.")
                driver.switch_to.window(ventana_principal)
        except Exception as e:
            logging.warning(f"⚠️ No se pudo limpiar emergentes: {e}")
            driver.switch_to.window(ventana_principal)

    try:
        # --------------------------------------------------
        # 1. Registrar archivos existentes ANTES
        # --------------------------------------------------
        archivos_antes = set(os.listdir(download_dir))

        # --------------------------------------------------
        # 2. Abrir el enlace y detectar el servidor
        # --------------------------------------------------
        logging.info(
            f"\n🌐 Abriendo enlace de descarga para: {nombre_video}"
        )
        driver.get(enlace_descarga)

        try:
            # 1. Esperar a que el navegador complete la carga de la página (hasta 15s)
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState")
                == "complete"
            )

            # 2. Pausa táctica para permitir que ejecute scripts internos/redirecciones
            time.sleep(3)

            # 3. Esperar opcionalmente a que cambie el título si la página sigue en carga inicial
            WebDriverWait(driver, 10).until(
                lambda d: d.title != "" and "Cargando" not in d.title
            )

        except Exception as e:
            logging.warning(
                f"⚠️ Tiempo de espera de redirección agotado en JKAnime: {e}"
            )

        # Detectar servidor utilizando la URL FINAL a la que llegó el navegador
        url_final = driver.current_url
        servidor = detectar_servidor_descarga(url_final)
        logging.info(
            f"🌐 Servidor final detectado tras redirección: {servidor} (URL: {url_final})"
        )

        # --------------------------------------------------
        # 2b. Guardián Anti-Redirección Prematura
        # --------------------------------------------------
        # Evita que el JS de la página secuestre la pestaña durante la carga inicial
        for reintento in range(3):
            time.sleep(2)
            url_actual = driver.current_url.lower()

            # Dominios o palabras clave de publicidad agresiva
            es_publicidad = any(
                p in url_actual
                for p in [
                    "signaldefendgo",
                    "clickid=",
                    "pets/rabbits",
                    "bdsclk",
                    "trk=",
                    "redirect",
                ]
            )

            # Si la URL no contiene el nombre del servidor o cayó en publicidad
            if es_publicidad or (servidor and servidor not in url_actual):
                logging.warning(
                    f"⚠️ Se detectó redirección publicitaria prematura ({url_actual[:45]}...). Volviendo a cargar enlace..."
                )
                driver.get(enlace_descarga)
            else:
                break

        # --------------------------------------------------
        # 3. Validación previa (Archivo caído)
        # --------------------------------------------------

        if servidor == "mega":
            logging.info("🔍 Verificando estado del archivo en Mega...")

            # Llamada a la función centralizada de validación
            if not validar_enlace_mega(driver, enlace_descarga):
                logging.error(
                    "❌ Error en Mega: El archivo ya no está disponible, fue eliminado o superó la cuota."
                )
                return "archivo_caido"
        else:
            logging.info("🔍 Verificando estado del archivo en Servidor...")

            if not validar_enlace_generico(driver, enlace_descarga):
                logging.error(
                    "❌ Error en Servidor: El archivo ya no está disponible, fue eliminado o error 404."
                )
                return "archivo_caido"

        # --------------------------------------------------
        # 4. Buscar botón correspondiente
        # --------------------------------------------------
        boton_descarga = encontrar_boton_descarga(driver, servidor)

        if boton_descarga is None:
            logging.error(
                f"❌ No se encontró botón de descarga para {nombre_video}"
            )
            return False

        # --------------------------------------------------
        # 5. Hacer clic (usando JavaScript para evadir bloqueos)
        # --------------------------------------------------
        ventana_principal = driver.current_window_handle
        driver.execute_script("arguments[0].click();", boton_descarga)
        logging.info(
            f"⬇️ Clic ejecutado. Iniciando verificación para: {nombre_video}"
        )
        cerrar_pestañas_publicitarias(driver, ventana_principal)

        # --------------------------------------------------
        # Flujo exclusivo para MP4UPLOAD
        # --------------------------------------------------
        if servidor == "mp4upload":
            logging.info(
                "🔄 Procesando Mp4Upload: Esperando habilitación del botón..."
            )

            # Control anti-redirección inicial
            asegurar_permanencia_en_servidor(
                driver, enlace_descarga, "mp4upload"
            )

            try:
                # --------------------------------------------------
                # PASO 2: Extraer enlace directo o limpiar superposiciones
                # --------------------------------------------------
                logging.info(
                    "⏳ Esperando la segunda página de Mp4Upload..."
                )

                boton_final = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "downloadbtn"))
                )

                # Opción A: Intentar extraer la URL directa de descarga del botón o su contenedor
                url_directa = None
                try:
                    url_directa = boton_final.get_attribute("href")
                    if not url_directa:
                        # Buscar si el botón está envuelto en un tag <a> o dentro de un <form>
                        padre_a = driver.find_elements(
                            By.XPATH, "//a[button[@id='downloadbtn']]"
                        )
                        if padre_a:
                            url_directa = padre_a[0].get_attribute("href")
                except Exception:
                    pass

                # Si encontramos la URL directa del video/archivo, forzamos la descarga directamente
                if url_directa and (
                    "mp4" in url_directa
                    or "download" in url_directa
                    or "d1." in url_directa
                ):
                    logging.info(
                        f"🔗 Enlace directo extraído con éxito. Forzando navegación..."
                    )
                    driver.get(url_directa)

                else:
                    # Opción B: Destruir overlays publicitarios invisibles y hacer clic limpio
                    logging.info(
                        "🛡️ Removiendo capas publicitarias invisibles..."
                    )
                    driver.execute_script(
                        """
                        // Eliminar div/iframes transparentes flotantes que secuestran el clic
                        document.querySelectorAll('div, iframe, a').forEach(el => {
                            let style = window.getComputedStyle(el);
                            if ((style.position === 'fixed' || style.position === 'absolute') && parseInt(style.zIndex) > 10) {
                                el.remove();
                            }
                        });
                        // Desvincular eventos onclick publicitarios del botón
                        let btn = document.getElementById('downloadbtn');
                        if (btn) btn.onclick = null;
                    """
                    )
                    time.sleep(1)

                    # Forzar la ejecución del envío o clic por JS nativo
                    logging.info(
                        "⬇️ Disparando descarga mediante evento JS...")
                    driver.execute_script("arguments[0].click();", boton_final)

                cerrar_pestañas_publicitarias(driver, ventana_principal)

            except Exception as e:
                logging.error(f"❌ Error durante el proceso en Mp4Upload: {e}")
                return False

        # --------------------------------------------------
        # Flujo blindado para VOE (2 Pasos)
        # --------------------------------------------------
        if servidor == "voe":
            logging.info("🔄 Procesando VOE: Buscando primer botón...")

            try:
                # --------------------------------------------------
                # PASO 1: Primer botón ("Descargar ahora")
                # --------------------------------------------------
                boton_paso1 = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "a.download-user-file, a[href*='download']",
                    ))
                )

                # TÁCTICA ANTI-ANUNCIOS: Extraer URL directa para saltarse la capa JS publicitaria
                url_paso1 = boton_paso1.get_attribute("href")

                if url_paso1 and "http" in url_paso1:
                    logging.info(
                        "🔗 Extrayendo enlace directo del paso 1. Navegando sin clics publicitarios..."
                    )
                    driver.get(url_paso1)
                else:
                    # Si no hay href accesible, destruir overlays y hacer clic por JS
                    driver.execute_script(
                        """
                        document.querySelectorAll('div, iframe, a').forEach(el => {
                            let style = window.getComputedStyle(el);
                            if ((style.position === 'fixed' || style.position === 'absolute') && parseInt(style.zIndex) > 10) {
                                el.remove();
                            }
                        });
                    """
                    )
                    driver.execute_script("arguments[0].click();", boton_paso1)

                cerrar_pestañas_publicitarias(driver, ventana_principal)
                time.sleep(2)

            except Exception as e:
                logging.error(f"❌ Error durante el proceso en VOE: {e}")
                return False

        if servidor == "mixdrop":
            logging.info(
                "🔄 Procesando Mixdrop: Esperando generación de href..."
            )

            href_final = None
            max_intentos = 6

            for intento in range(1, max_intentos + 1):
                try:
                    # Buscar botones con la clase de descarga de Mixdrop
                    botones = driver.find_elements(
                        By.CSS_SELECTOR, "a.download-btn"
                    )

                    for btn in botones:
                        url_href = btn.get_attribute("href")
                        # Si ya se generó el href (Botón 3), guardarlo y salir del bucle
                        if url_href and "http" in url_href:
                            href_final = url_href
                            logging.info(
                                f"🎯 ¡Enlace de descarga obtenido en intento {intento}!: {href_final}"
                            )
                            break

                    if href_final:
                        break

                    logging.info(
                        f"⏳ Intento {intento}/{max_intentos}: href no detectado. Presionando Botón 2 con eventos reales..."
                    )

                    if botones:
                        boton_actual = botones[0]

                        # Clic simulado con movimiento de ratón real
                        try:
                            actions = ActionChains(driver)
                            actions.move_to_element(
                                boton_actual
                            ).click().perform()
                        except Exception:
                            # Respaldo por eventos de mouse JS si ActionChains falla
                            driver.execute_script(
                                """
                                var el = arguments[0];
                                var evObj = document.createEvent('MouseEvents');
                                evObj.initEvent('click', true, true);
                                el.dispatchEvent(evObj);
                            """,
                                boton_actual,
                            )

                    cerrar_pestañas_publicitarias(driver, ventana_principal)
                    time.sleep(3)  # Tiempo para la animación / temporizador

                except Exception as e:
                    logging.warning(f"⚠️ Error interactuando con Mixdrop: {e}")
                    time.sleep(2)

            # Ejecutar descarga usando el href obtenido
            if href_final:
                logging.info(
                    "⬇️ Navegando / ejecutando clic directo en el archivo de Mixdrop..."
                )
                driver.get(href_final)
            else:
                logging.error(
                    "❌ No se logró generar el enlace 'href' en Mixdrop."
                )
                return False

        if servidor == "gofile":
            logging.info("🔄 Procesando Gofile: Buscando botón de descarga...")

            # Control anti-redirección inicial
            asegurar_permanencia_en_servidor(
                driver, enlace_descarga, "gofile"
            )

            try:
                # --------------------------------------------------
                # PASO 1: Localizar botón de descarga ("Download")
                # --------------------------------------------------
                boton_descarga = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "button[data-action='download'], button[title='Download']",
                    ))
                )

                # Intentar extraer URL directa si existe en atributos de enlace/data
                url_directa = boton_descarga.get_attribute("href") or boton_descarga.get_attribute("data-url")

                if url_directa and "http" in url_directa:
                    logging.info(
                        "🔗 Extrayendo enlace directo. Navegando sin clics publicitarios..."
                    )
                    driver.get(url_directa)
                else:
                    # Destruir overlays o anuncios flotantes y hacer clic con JavaScript
                    driver.execute_script(
                        """
                        document.querySelectorAll('div, iframe, a').forEach(el => {
                            let style = window.getComputedStyle(el);
                            if ((style.position === 'fixed' || style.position === 'absolute') && parseInt(style.zIndex) > 10) {
                                el.remove();
                            }
                        });
                    """
                    )
                    driver.execute_script("arguments[0].click();", boton_descarga)

                cerrar_pestañas_publicitarias(driver, ventana_principal)
                time.sleep(2)

            except Exception as e:
                logging.error(f"❌ Error durante el proceso en Gofile: {e}")
                return False

        # --------------------------------------------------
        # 6. Verificación POST-CLIC para MEGA (Cuota Agotada)
        # --------------------------------------------------
        if servidor == "mega":
            try:
                # Espera dinámica para la aparición del modal de cuota
                modal_cuota = WebDriverWait(driver, 30).until(
                    EC.visibility_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            ".quota-dialog.transfer-quota.active",
                        )
                    )
                )

                if modal_cuota and modal_cuota.is_displayed():
                    logging.warning(
                        "⚠️ Error en Mega: Se ha agotado la cuota de transferencia tras presionar descargar."
                    )
                    return "cuota_agotada"

            except Exception:
                # Si expira el tiempo de espera, el modal no apareció (descarga correcta)
                logging.info(
                    "✅ Sin bloqueos de cuota detectados en MEGA. Procesando archivo..."
                )

        # --------------------------------------------------
        # 7. Esperar confirmación REAL del archivo en disco
        # --------------------------------------------------
        archivo_descargado = verificar_descarga(
            download_dir=download_dir,
            archivos_antes=archivos_antes,
            tiempo_maximo=1800,  # 30 minutos
            intervalo=2,
            tiempo_estable=6,
        )

        # --------------------------------------------------
        # 8. Resultado final
        # --------------------------------------------------
        if archivo_descargado:
            logging.info(f"✅ DESCARGA COMPLETADA: {nombre_video}")
            logging.info(
                f"📁 Archivo: {os.path.basename(archivo_descargado)}"
            )
            return True

        logging.error(
            f"❌ La descarga NO pudo confirmarse: {nombre_video}"
        )
        return False

    except Exception as e:
        logging.error(f"❌ Error descargando {nombre_video}: {e}")
        return False


def descargar_video_con_reintentos(
    video,
    download_dir,
    max_intentos=3
):
    """
    Intenta descargar un video varias veces.
    Crea un driver nuevo en cada intento.
    """

    for intento in range(1, max_intentos + 1):

        logging.info(
            f"\nIntento {intento}/{max_intentos}"
        )

        driver = None

        try:

            driver = configurar_navegador(
                download_dir
            )

            if driver is None:
                raise Exception(
                    "No se pudo iniciar ChromeDriver."
                )

            resultado = hacer_click_en_boton_descarga(
                driver,
                video["link_descarga"],
                download_dir,
                video["nombre"],
                video.get('fuente')
            )

            # Si la descarga fue exitosa
            if resultado is True:
                logging.info(
                    f"✅ Descarga completada: "
                    f"{video['nombre']}"
                )
                return True

            # Si detectó un error crítico de cuota o archivo caído, detiene los reintentos inmediatamente y lo propaga
            if resultado in ["archivo_caido", "cuota_agotada"]:
                return resultado

            logging.error(
                f"❌ Falló el intento "
                f"{intento}/{max_intentos}"
            )

        except Exception as e:

            logging.error(
                f"❌ Error en intento "
                f"{intento}/{max_intentos}: {e}"
            )

        finally:

            if driver is not None:

                try:
                    driver.quit()
                    logging.info("🔒 Driver cerrado.")

                except Exception as e:

                    logging.error(
                        f"⚠️ Error cerrando driver: {e}"
                    )

        if intento < max_intentos:

            espera = intento * 10

            logging.info(
                f"🔄 Reintentando en "
                f"{espera} segundos..."
            )

            time.sleep(espera)

    return False


# ==========================================
# MEJORA 3: VALIDACIÓN DE TODOS LOS SERVIDORES DE UNA FUENTE
# ==========================================

def recopilar_servidores_candidatos(video):
    """
    Junta TODOS los servidores que ofrece una fuente para un episodio:
    la lista video['servidores'] (si existe) + video['link_descarga'].
    Devuelve [{"servidor": "Mega", "enlace": "https://..."}, ...] sin repetidos.
    """
    candidatos = []
    vistos = set()

    for s in video.get("servidores") or []:
        enlace = s.get("enlace")
        if not enlace or enlace in vistos:
            continue
        vistos.add(enlace)
        candidatos.append({
            "servidor": s.get("servidor") or nombre_servidor_desde_url(enlace),
            "enlace": enlace,
        })

    principal = video.get("link_descarga")
    # La página del episodio NO es un enlace de descarga
    if principal and principal == video.get("enlace"):
        principal = None
    if principal and principal != "No encontrado" and principal not in vistos:
        candidatos.insert(0, {
            "servidor": video.get("servidor_seleccionado") or nombre_servidor_desde_url(principal),
            "enlace": principal,
        })

    return candidatos


def validar_servidor(driver, servidor, enlace):
    """Valida un enlace según su tipo de servidor (Mega o genérico)."""
    es_mega = (
        "mega" in (servidor or "").lower()
        or nombre_servidor_desde_url(enlace) == "mega"
    )
    if es_mega:
        return validar_enlace_mega(driver, enlace)
    return validar_enlace_generico(driver, enlace)


def validar_todos_los_servidores(driver, video, servidores_bloqueados=None):
    """
    Valida CADA servidor que ofrece la fuente (no se detiene en el primero).

    - Guarda los funcionales en video['servidores_validos'].
    - Deja el primero como video['link_descarga'] / ['servidor_seleccionado'].
    - Devuelve True si hay al menos uno disponible; False si ninguno sirve
      (en ese caso hay que pasar a la siguiente fuente).

    servidores_bloqueados: conjunto de nombres ('mega', ...) que no deben
    usarse (p. ej. Mega sin cuota en esta ejecución).
    """
    bloqueados = {b.lower() for b in (servidores_bloqueados or set())}
    fuente = video.get("fuente", "Desconocida")
    candidatos = recopilar_servidores_candidatos(video)

    if not candidatos:
        logging.warning(f"⚠️ La fuente '{fuente}' no entregó ningún servidor.")
        video["servidores_validos"] = []
        return False

    logging.info(
        f"🔍 Fuente '{fuente}': validando {len(candidatos)} servidor(es) antes de descargar...")

    validos = []

    for c in candidatos:
        nombre = c["servidor"]
        clave = nombre_servidor_desde_url(c["enlace"])

        if str(nombre).lower() in bloqueados or clave in bloqueados:
            logging.info(
                f"⏭️ Servidor '{nombre}' omitido (bloqueado en esta ejecución).")
            continue

        logging.info(f"   ↪ Probando '{nombre}' -> {c['enlace']}")

        if validar_servidor(driver, nombre, c["enlace"]):
            logging.info(f"   ✅ '{nombre}' disponible")
            validos.append(c)
        else:
            logging.warning(f"   ❌ '{nombre}' caído o inaccesible")

    video["servidores_validos"] = validos

    if not validos:
        logging.error(
            f"❌ Ningún servidor disponible en la fuente '{fuente}'.")
        return False

    video["link_descarga"] = validos[0]["enlace"]
    video["servidor_seleccionado"] = validos[0]["servidor"]
    return True


def evaluar_video_de_fuente(driver, video, nombre_esperado, episodio_esperado, servidores_bloqueados=None):
    """
    Evalúa el resultado de UNA fuente:
        1) ¿es el anime/temporada/episodio correcto?
        2) ¿hay al menos un servidor disponible?
    Devuelve (valido, motivo).
    """
    fuente = video.get("fuente", "Desconocida")

    coincide, motivo = validar_coincidencia_anime(
        video, nombre_esperado, episodio_esperado)
    if not coincide:
        logging.error(
            f"🚫 '{fuente}' devolvió algo que NO coincide con "
            f"'{nombre_esperado}' Ep {episodio_esperado}: {motivo}"
        )
        return False, f"no coincide ({motivo})"

    # TioAnime entrega la página del episodio; hay que extraer el enlace de descarga.
    # Solo se sobrescribe link_descarga si realmente se encontró uno.
    if (
        str(fuente).lower() == "tioanime"
        and not video.get("servidores")
        and video.get("enlace")
        and (not video.get("link_descarga")
             or video.get("link_descarga") == video.get("enlace"))
    ):
        enlace_dl = buscar_boton_descarga(driver, video["enlace"])
        if enlace_dl:
            video["link_descarga"] = enlace_dl

    if validar_todos_los_servidores(driver, video, servidores_bloqueados):
        return True, "ok"

    return False, "ningún servidor disponible"


def buscar_fuente_alternativa(driver, nombre, episodio, lista_excluidas, download_dir, servidores_bloqueados=None):
    """
    Recorre las fuentes restantes hasta encontrar una que:
      - devuelva el anime/temporada/episodio correcto, y
      - tenga al menos un servidor disponible.
    Modifica 'lista_excluidas' agregando cada fuente descartada.
    Devuelve el video válido o None si se agotaron las fuentes.
    """
    while True:
        logging.info(
            f"🚫 Fuentes descartadas: {', '.join(lista_excluidas) or 'ninguna'}")

        encontrados = buscar_en_fuentes(
            [{"nombre": nombre, "episodio_buscado": episodio}],
            FUENTES_ANIME,
            excluir_fuente=lista_excluidas,
            download_dir=download_dir,
        )

        if not encontrados:
            return None

        excluidas_lower = {f.lower() for f in lista_excluidas}
        hubo_nuevas = False

        for v_alt in encontrados:
            fuente_alt = v_alt.get("fuente", "Desconocida")

            if str(fuente_alt).lower() in excluidas_lower:
                continue  # el buscador ignoró la exclusión; evita bucle infinito

            hubo_nuevas = True

            valido, motivo = evaluar_video_de_fuente(
                driver, v_alt, nombre, episodio, servidores_bloqueados)

            if valido:
                logging.info(
                    f"✅ Fuente alternativa '{fuente_alt}' válida "
                    f"({v_alt.get('servidor_seleccionado')}) para: {nombre}"
                )
                return v_alt

            logging.error(f"❌ Fuente '{fuente_alt}' descartada: {motivo}")
            lista_excluidas.append(fuente_alt)
            excluidas_lower.add(str(fuente_alt).lower())

        if not hubo_nuevas:
            return None


# --------------------------------------------------
# Servidores alternos compartidos entre fase nube y fase local
# --------------------------------------------------
# Google Sheets solo guarda UN enlace por episodio, así que los demás
# servidores ya validados se guardan en un JSON local. Si la fase nube y la
# local corren en máquinas distintas, habría que guardar esto en una columna
# extra de la hoja.

def _clave_episodio(nombre, episodio):
    return f"{normalizar_texto(nombre)}|{episodio}"


def guardar_servidores_alternos(nombre, episodio, fuente, servidores):
    try:
        datos = {}
        if os.path.exists(ARCHIVO_SERVIDORES_ALTERNOS):
            with open(ARCHIVO_SERVIDORES_ALTERNOS, "r", encoding="utf-8") as f:
                datos = json.load(f)

        datos[_clave_episodio(nombre, episodio)] = {
            "fuente": fuente,
            "servidores": servidores or [],
            "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(ARCHIVO_SERVIDORES_ALTERNOS, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)

    except Exception as e:
        logging.warning(f"⚠️ No se pudieron guardar servidores alternos: {e}")


def cargar_servidores_alternos(nombre, episodio, fuente):
    """Servidores ya validados de ESA misma fuente para ese episodio."""
    try:
        if not os.path.exists(ARCHIVO_SERVIDORES_ALTERNOS):
            return []
        with open(ARCHIVO_SERVIDORES_ALTERNOS, "r", encoding="utf-8") as f:
            datos = json.load(f)

        registro = datos.get(_clave_episodio(nombre, episodio))
        if not registro:
            return []
        if str(registro.get("fuente", "")).lower() != str(fuente or "").lower():
            return []
        return registro.get("servidores", [])

    except Exception as e:
        logging.warning(f"⚠️ No se pudieron leer servidores alternos: {e}")
        return []


# ==========================================
# MÓDULO 1: BÚSQUEDA, VALIDACIÓN Y SHEETS (NUBE)
# ==========================================

def validar_enlace_unico(driver, video):
    """Compatibilidad: ahora valida TODOS los servidores de la fuente."""
    return validar_todos_los_servidores(driver, video)


def obtener_primer_enlace_valido(driver, video):
    """Compatibilidad: ahora valida TODOS los servidores de la fuente."""
    return validar_todos_los_servidores(driver, video)


def validar_enlace_generico(driver, enlace):
    """
    Validación básica para servidores como VOE, Mixdrop, Mp4upload, etc.
    """
    try:
        driver.get(enlace)
        time.sleep(5)
        texto_pagina = driver.page_source.lower()

        # Mensajes de error comunes en servidores de video (todo en minúsculas,
        # porque texto_pagina ya está en minúsculas)
        errores_comunes = [
            "error 404",
            "no puede encontrar",
            "we are sorry",
            "find the file",
            "file not found",
            "video not found",
            "file was deleted",
            "has been deleted",
        ]

        if any(err in texto_pagina for err in errores_comunes):
            return False

        return True
    except Exception as e:
        logging.error(f"Error comprobando {enlace}: {e}")
        return False


def validar_enlace_mega(driver, enlace):
    """
    Entra al enlace de Mega y comprueba si el archivo está disponible
    y con cuota de transferencia activa.
    Devuelve True si es válido, False si está caído.
    """

    if not enlace or "mega" not in enlace.lower():
        return True  # Si no es de Mega, lo damos por bueno por defecto

    try:
        driver.get(enlace)
        time.sleep(10)
        texto_pagina = driver.page_source.lower()

        # Si encuentra errores típicos de Mega, retorna False
        if any(error in texto_pagina for error in [
            "el archivo ya no está disponible",
            "archivo no encontrado",
            "acceder al archivo",
            "el archivo ya no",
        ]):
            return False

        return True  # Todo OK

    except Exception:
        return False  # Si hubo un error de red o carga, consideramos que falló


def flujo_descarga_animes(file_name, download_dir):

    mensaje_telegram = ""

    # Leer los datos desde el archivo .json / .txt
    datos_crudos = leer_nombres_desde_txt(file_name)

    if not datos_crudos:
        logging.error("❌ No hay animes pendientes para buscar.")
        return False

    # 2. Expandir los animes según sus episodios pendientes PRIMERO
    animes_a_expandir = []

    for item in datos_crudos:
        nombre = item.get("nombre")
        episodio_actual = item.get("episodio_actual", 0)
        pendientes = item.get("pendientes", 0)

        if pendientes > 0:
            for i in range(1, pendientes + 1):
                ep_buscado = episodio_actual + i
                animes_a_expandir.append({
                    "nombre": nombre,
                    "episodio_buscado": ep_buscado
                })
        else:
            animes_a_expandir.append(item)

    if not animes_a_expandir:
        logging.error("❌ No hay episodios pendientes para procesar.")
        return False

    # ☁️ FILTRO INTELIGENTE DE GOOGLE SHEETS (Nombre + Episodio)
    # ==================================================================
    logging.info(
        "☁️ Conectando con Google Sheets para verificar el historial previo...")
    sheet_service = obtener_conexion_google_sheets()

    # ⚠️ IMPORTANTE: Debe leer TODAS las filas de Sheets (incluyendo 'Completado')
    # Si 'leer_animes_pendientes' filtra antes, usa una función que traiga la hoja completa.
    animes_en_sheet = leer_animes_pendientes(
        sheet_service) if sheet_service else []

    animes_a_buscar = []

    for anime_obj in animes_a_expandir:
        nombre_obj = anime_obj.get("nombre", "").strip().lower()
        ep_obj = str(anime_obj.get("episodio_buscado", "")).strip()

        # Busca si ESTE capítulo exacto (ej. Ep 10) ya tiene un registro en Sheets
        registro_existente = next(
            (a for a in animes_en_sheet
             if a["nombre"].strip().lower() == nombre_obj and str(a["episodio"]).strip() == ep_obj),
            None
        )

        if not registro_existente:
            # Caso A: El episodio NO existe en Sheets -> Se debe buscar
            animes_a_buscar.append(anime_obj)
        else:
            estado = registro_existente.get("estado", "").strip().upper()

            # Caso B: Si requiere Cambiar Fuente -> Se procesa
            if estado in ["CAMBIAR FUENTE"]:
                if registro_existente.get("fuente_fallida"):
                    anime_obj["fuente_fallida"] = registro_existente.get(
                        "fuente_fallida")
                animes_a_buscar.append(anime_obj)
            else:
                # Caso C: Estado 'COMPLETADO', 'DESCARGADO', etc. -> Se omite
                logging.info(
                    f"⏩ Omitiendo '{anime_obj.get('nombre')}' (Ep. {ep_obj}): Ya registrado como '{registro_existente.get('estado')}' en Google Sheets."
                )

    if not animes_a_buscar:
        logging.info(
            "✅ Todos los episodios pendientes ya estaban descargados en Google Sheets."
        )
        mensaje = "✅ <b>Animes al día</b>\nTodos los episodios pendientes ya se encuentran descargados."
        enviar_mensaje_telegram(mensaje)
        return False
    # ==================================================================

    # Paso 1: Buscar videos relacionados únicamente con los que pasaron el filtro
    logging.info("Buscando videos relacionados...")
    videos_encontrados = buscar_en_fuentes(
        animes_a_buscar,
        FUENTES_ANIME,
        download_dir=download_dir
    )

    with open("videos_encontrados.txt", "w", encoding="utf-8") as archivo_txt:
        json.dump(videos_encontrados, archivo_txt,
                  ensure_ascii=False, indent=4)

    # ==================================================================
    # 📲 NOTIFICACIÓN SI NO SE ENCONTRARON VIDEOS
    # ==================================================================
    if not videos_encontrados:
        lineas = [
            "⚠️ <b>No se encontraron episodios en la búsqueda</b>\n",
            "<b>Episodios consultados sin resultados:</b>"
        ]

        for item in animes_a_buscar:
            # html.escape evita errores en Telegram si el nombre contiene '<', '>' o '&'
            nombre = html.escape(str(item.get("nombre", "Sin nombre")))
            ep = item.get("episodio_buscado", item.get("episodio_actual", "?"))
            lineas.append(f"• <b>{nombre}</b> — Ep. {ep}")

        mensaje_telegram = "\n".join(lineas)

        logging.info("No se encontraron videos para los animes indicados.")

        # Envío a Telegram
        enviar_mensaje_telegram(mensaje_telegram)

        return False

    # (antes no se devolvía el resultado)
    return proceso_nube_buscar_y_guardar_sheets(download_dir, videos_encontrados)


def _registrar_video_valido(sheet_service, video, nombre, episodio, fecha, fuentes_fallidas=None, prefijo_captura="Link_"):
    """Captura, guarda servidores alternos y actualiza Google Sheets."""
    fuente = video.get("fuente", "Desconocida")

    try:
        tomar_captura_express(
            url=video["link_descarga"],
            nombre_fuente=prefijo_captura + str(fuente),
            nombre_anime=nombre,
            episodio=episodio
        )
    except Exception as e:
        logging.warning(f"⚠️ No se pudo tomar la captura: {e}")

    guardar_servidores_alternos(
        nombre, episodio, fuente, video.get("servidores_validos", []))

    if sheet_service:
        kwargs = dict(
            sheet_service=sheet_service,
            nombre_hoja="Animes",
            nombre_anime=nombre,
            episodio=episodio,
            nuevo_enlace=video["link_descarga"],
            nueva_fuente=fuente,
            nuevo_estado="Pendiente",
            fecha_actualizacion=fecha,
            crear_si_no_existe=True,
        )
        if fuentes_fallidas is not None:
            kwargs["fuentes_fallidas"] = fuentes_fallidas
        actualizar_estado_google_sheets(**kwargs)


def proceso_nube_buscar_y_guardar_sheets(download_dir, videos_encontrados, resetear_fuentes_previas=False):
    """
    Valida que cada resultado sea el anime/temporada/episodio correcto,
    valida TODOS los servidores de la fuente, y si ninguno sirve pasa a la
    siguiente fuente. Actualiza Google Sheets y genera los respaldos locales.
    """
    # 1. Obtener conexión con Google Sheets al inicio para las actualizaciones en tiempo real
    sheet_service = obtener_conexion_google_sheets()
    if not sheet_service:
        logging.warning(
            "⚠️ No se pudo conectar con Google Sheets. Se trabajará en modo local.")

    # 2. Configurar el navegador
    driver = configurar_navegador(download_dir)

    if driver is None:
        logging.error(
            "❌ No se pudo iniciar el navegador para obtener los enlaces de descarga.")
        return False

    videos_finales = []

    try:
        # ----------------------------------------------------------------------
        # A. Extracción inicial de enlaces
        # ----------------------------------------------------------------------
        fuente_detectada = (
            videos_encontrados[0].get("fuente", "Desconocida")
            if videos_encontrados
            else "Desconocida"
        )

        logging.info(
            f"ℹ️ Fuente ({fuente_detectada}) detectada. Validando enlace...")
        videos_brutos = videos_encontrados

        with open("videos_brutos.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(videos_brutos, archivo_txt, ensure_ascii=False, indent=4)

        if not videos_brutos:
            logging.error(
                "❌ No se obtuvieron enlaces de descarga para validar.")
            return []

        # ----------------------------------------------------------------------
        # B. Validación (coincidencia + servidores) y re-búsqueda en cascada
        # ----------------------------------------------------------------------
        logging.info("\n🔎 Validando resultados y estado de los servidores...")

        for video in videos_brutos:
            nombre_servidor = video.get("nombre_anime") or video.get("nombre")
            episodio_servidor = video.get(
                "episodio_buscado") or video.get("episodio")
            episodio_limpio = (
                int(episodio_servidor)
                if str(episodio_servidor).isdigit()
                else episodio_servidor
            )
            fecha_ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # --- CASO A: la fuente principal es correcta y tiene algún servidor válido ---
            valido, motivo = evaluar_video_de_fuente(
                driver, video, nombre_servidor, episodio_limpio)

            if valido:
                logging.info(
                    f"✅ Enlace válido ({video.get('servidor_seleccionado')}) para: {nombre_servidor}")
                video["estado"] = "Pendiente"

                _registrar_video_valido(
                    sheet_service, video, nombre_servidor, episodio_limpio,
                    fecha_ahora, prefijo_captura="Link_"
                )

                videos_finales.append(video)
                continue

            # --- CASO B: la fuente principal falló -> Re-búsqueda en cascada ---
            logging.error(
                f"❌ Fuente inicial descartada para {nombre_servidor} ({motivo}). Buscando fuentes alternativas...")

            if resetear_fuentes_previas:
                lista_excluidas = []
            else:
                fallidas_previas_str = video.get("fuentes_fallidas", "")
                lista_excluidas = [
                    f.strip() for f in fallidas_previas_str.split(",") if f.strip()]

            fuente_actual = video.get("fuente", "Desconocida")
            if fuente_actual and fuente_actual not in lista_excluidas:
                lista_excluidas.append(fuente_actual)

            v_alt = buscar_fuente_alternativa(
                driver, nombre_servidor, episodio_limpio, lista_excluidas, download_dir
            )

            if v_alt:
                v_alt["estado"] = "Pendiente"
                v_alt["fuentes_fallidas"] = ", ".join(lista_excluidas)

                _registrar_video_valido(
                    sheet_service, v_alt, nombre_servidor, episodio_limpio,
                    fecha_ahora,
                    fuentes_fallidas=v_alt["fuentes_fallidas"],
                    prefijo_captura="Link Alterno "
                )

                videos_finales.append(v_alt)
                continue

            # --- CASO C: Se agotaron todas las fuentes sin éxito ---
            cadena_final_fallidas = ", ".join(lista_excluidas)

            # Escapar variables dinámicas para prevenir errores de parseo HTML en Telegram
            nombre_esc = html.escape(str(nombre_servidor))
            episodio_esc = html.escape(str(episodio_limpio))
            fuentes_esc = html.escape(str(cadena_final_fallidas))

            msg_error = (
                f"🚨 <b>Alerta:</b> Se agotaron todas las fuentes para: <b>{nombre_esc} Episodio {episodio_esc}</b>\n"
                f"📝 Fuentes probadas: {fuentes_esc}\n"
                "⏱️ Marcado como 'Sin Fuentes'. Se reintentará en el próximo ciclo."
            )
            logging.error(msg_error)
            enviar_mensaje_telegram(msg_error)

            video["estado"] = "Sin Fuentes"
            video["fuentes_fallidas"] = cadena_final_fallidas

            if sheet_service:
                actualizar_estado_google_sheets(
                    sheet_service=sheet_service,
                    nombre_hoja="Animes",
                    nombre_anime=nombre_servidor,
                    episodio=episodio_limpio,
                    fuentes_fallidas=cadena_final_fallidas,
                    nuevo_estado="Sin Fuentes",
                    fecha_actualizacion=fecha_ahora,
                    crear_si_no_existe=True
                )

            videos_finales.append(video)

        # --- FUERA DEL BUCLE: Consolidación y Notificación Única ---
        if sheet_service and videos_finales:
            logging.info(
                "📊 Consolidando historial en Google Sheets y enviando resumen final...")
            guardar_y_actualizar_historial_sheets(
                sheet_service=sheet_service,
                resultados_animes=videos_finales
            )

        # ----------------------------------------------------------------------
        # C. Generación de respaldos locales y retorno
        # ----------------------------------------------------------------------
        with open("videos_finales.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(videos_finales, archivo_txt,
                      ensure_ascii=False, indent=4)

        # Solo los que realmente quedaron listos (los 'Sin Fuentes' ya no se arrastran)
        videos_validos = [
            v for v in videos_finales
            if v.get("estado") == "Pendiente" and v.get("link_descarga")
        ]

        if not videos_validos:
            logging.error(
                "❌ No se encontraron videos finales válidos para guardar.")
            return []

        guardar_resultados_videos_txt(
            videos_validos, "resultados_videos_con_descarga.txt")
        logging.info("🎉 Proceso en la nube finalizado con éxito.")

        return videos_validos

    finally:
        # El bloque 'finally' asegura la salida del driver sin importar si hubo error o no
        try:
            driver.quit()
            logging.info("🔒 Driver de búsqueda cerrado correctamente.")
        except Exception as e:
            logging.error(f"⚠️ Error al cerrar el driver: {e}")


# ==========================================
# MÓDULO 2: DESCARGA LOCAL Y ACTUALIZACIÓN
# ==========================================

def _notificar_cambio(nombre, episodio, motivo, servidor_anterior, fuente_anterior,
                      servidor_nuevo, fuente_nueva, misma_fuente=False):
    """
    MEJORA 2: mensaje de Telegram que indica el servidor NUEVO (Mega, VOE, ...).
    """
    n = html.escape(str(nombre))
    e = html.escape(str(episodio))
    m = html.escape(str(motivo))
    s_ant = html.escape(str(servidor_anterior))
    f_ant = html.escape(str(fuente_anterior))
    s_nue = html.escape(str(servidor_nuevo))
    f_nue = html.escape(str(fuente_nueva))

    titulo = "🔁 <b>Cambiando de Servidor</b>" if misma_fuente else "🔄 <b>Cambiando de Fuente</b>"

    enviar_mensaje_telegram(
        f"{titulo}\n\n"
        f"🎬 Anime: <b>{n}</b>\n"
        f"📺 Episodio: <b>{e}</b>\n"
        f"🔴 Motivo: <b>{m}</b>\n\n"
        f"⬅️ Antes: <b>{s_ant}</b> ({f_ant})\n"
        f"✅ Ahora: <b>{s_nue}</b> ({f_nue})"
    )


def _siguiente_servidor_misma_fuente(driver, video, nombre, episodio, enlaces_fallidos, servidores_bloqueados):
    """
    Busca, entre los servidores ya validados de la MISMA fuente, uno que no
    haya fallado todavía (lo vuelve a validar porque pudo caerse mientras tanto).
    """
    fuente = video.get("fuente", "Desconocida")
    bloqueados = {b.lower() for b in servidores_bloqueados}

    for s in cargar_servidores_alternos(nombre, episodio, fuente):
        enlace = s.get("enlace")
        if not enlace or enlace in enlaces_fallidos:
            continue

        if (
            str(s.get("servidor", "")).lower() in bloqueados
            or nombre_servidor_desde_url(enlace) in bloqueados
        ):
            continue

        logging.info(
            f"🔍 Probando otro servidor de '{fuente}': {s.get('servidor')} -> {enlace}")

        if validar_servidor(driver, s.get("servidor"), enlace):
            return s

        logging.warning(f"⚠️ Servidor alterno también caído: {s.get('servidor')}")
        enlaces_fallidos.add(enlace)

    return None


def procesar_descarga_video(video, driver_servidor, sheet_service, download_dir, servidores_sin_cuota):
    """
    Descarga un episodio. Si el servidor falla por archivo caído o cuota:
        1) prueba los otros servidores ya validados de la misma fuente,
        2) si no hay, busca otra fuente (validando todos sus servidores),
        3) REINTENTA la descarga con el nuevo enlace y repite si vuelve a fallar
           (hasta MAX_CAMBIOS_FUENTE cambios).
    Devuelve True si se descargó, False en caso contrario.
    """
    nombre = video.get("nombre_anime") or video.get("nombre")
    episodio = video.get("episodio_buscado") or video.get("episodio")
    episodio_limpio = int(episodio) if str(episodio).isdigit() else episodio

    nombre_esc = html.escape(str(nombre))
    episodio_esc = html.escape(str(episodio_limpio))

    carpeta_dia = obtener_directorio_fecha(download_dir)

    lista_excluidas = [
        f.strip() for f in str(video.get("fuentes_fallidas", "")).split(",") if f.strip()
    ]
    enlaces_fallidos = set()
    cambios = 0

    while True:
        fecha_ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        servidor_actual = nombre_servidor_desde_url(video.get("link_descarga"))

        # Si Mega ya se quedó sin cuota en esta ejecución, ni lo intentamos
        if servidor_actual in servidores_sin_cuota:
            logging.warning(
                f"⏭️ '{servidor_actual}' sin cuota en esta ejecución. Se omite la descarga directa.")
            resultado = "cuota_agotada"
        else:
            resultado = descargar_video_con_reintentos(
                video, carpeta_dia, max_intentos=3)

        with open("resultados.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(resultado, archivo_txt, ensure_ascii=False, indent=4)

        # ---------------------------------------------------------------------
        # OPCIÓN A: Éxito real de la descarga
        # ---------------------------------------------------------------------
        if resultado is True:
            logging.info(
                f"✅ Descarga completada correctamente para: {nombre}")

            servidor_ok = nombre_servidor_legible(
                video.get("servidor_seleccionado"), video.get("link_descarga"))

            enviar_mensaje_telegram(
                f"📥 <b>Descarga Exitosa</b>\n\n"
                f"🎬 Anime: <b>{nombre_esc}</b>\n"
                f"📺 Episodio: <b>{episodio_esc}</b>\n"
                f"🖥️ Servidor: <b>{html.escape(servidor_ok)}</b> ({html.escape(str(video.get('fuente')))})\n"
                f"🟢 Estado: Completado."
            )

            if nombre and episodio:
                actualizar_estado_google_sheets(
                    sheet_service=sheet_service,
                    nombre_hoja="Animes",
                    nombre_anime=nombre,
                    episodio=episodio,
                    nuevo_estado="Completado"
                )

                marcar_anime_descargado_con_selenium(
                    driver_servidor, nombre, episodio)

            return True

        # ---------------------------------------------------------------------
        # OPCIÓN C: Retornó False (fallaron los 3 intentos sin ser caído/cuota)
        # ---------------------------------------------------------------------
        if resultado not in ["archivo_caido", "cuota_agotada"]:
            logging.error(
                f"❌ Fallaron los 3 intentos de descarga para: {nombre}")

            enviar_mensaje_telegram(
                f"⚠️ <b>Fallo de Descarga</b>\n\n🎬 Anime: <b>{nombre_esc}</b>\n📺 Episodio: <b>{episodio_esc}</b>\n🔴 Motivo: Agotados 3 reintentos (timeout o botón no interactuable)."
            )

            actualizar_estado_google_sheets(
                sheet_service=sheet_service,
                nombre_hoja="Animes",
                nombre_anime=nombre,
                episodio=episodio,
                nuevo_estado="Cambiar Fuente"
            )
            return False

        # ---------------------------------------------------------------------
        # OPCIÓN B: Fallo crítico (archivo caído o cuota agotada)
        # ---------------------------------------------------------------------
        estado_error = "Archivo Caído" if resultado == "archivo_caido" else "Cuota Agotada"

        enlace_fallido = video.get("link_descarga")
        servidor_fallido = nombre_servidor_legible(
            video.get("servidor_seleccionado"), enlace_fallido)
        fuente_anterior = video.get("fuente", "Desconocida")

        enlaces_fallidos.add(enlace_fallido)

        if resultado == "cuota_agotada":
            clave = nombre_servidor_desde_url(enlace_fallido)
            if clave != "desconocido":
                servidores_sin_cuota.add(clave)

        cambios += 1
        logging.error(
            f"❌ {estado_error} en {servidor_fallido} ({fuente_anterior}) para {nombre} Ep {episodio_limpio}. "
            f"Cambio {cambios}/{MAX_CAMBIOS_FUENTE}..."
        )

        if cambios > MAX_CAMBIOS_FUENTE:
            logging.error("❌ Se alcanzó el máximo de cambios de fuente.")
            actualizar_estado_google_sheets(
                sheet_service=sheet_service,
                nombre_hoja="Animes",
                nombre_anime=nombre,
                episodio=episodio_limpio,
                fuentes_fallidas=", ".join(lista_excluidas),
                fecha_actualizacion=fecha_ahora,
                nuevo_estado="Sin Fuentes"
            )
            enviar_mensaje_telegram(
                f"⚠️ <b>Alerta: Demasiados cambios de fuente</b>\n\n🎬 Anime: <b>{nombre_esc}</b>\n📺 Episodio: <b>{episodio_esc}</b>\n🔴 Estado: <b>Sin Fuentes</b>"
            )
            return False

        # ---- 1) Otro servidor de la MISMA fuente ----
        s_alterno = _siguiente_servidor_misma_fuente(
            driver_servidor, video, nombre, episodio_limpio,
            enlaces_fallidos, servidores_sin_cuota
        )

        if s_alterno:
            video["link_descarga"] = s_alterno["enlace"]
            video["servidor_seleccionado"] = s_alterno["servidor"]

            actualizar_estado_google_sheets(
                sheet_service=sheet_service,
                nombre_hoja="Animes",
                nombre_anime=nombre,
                episodio=episodio_limpio,
                nuevo_enlace=s_alterno["enlace"],
                nueva_fuente=fuente_anterior,
                fecha_actualizacion=fecha_ahora,
                nuevo_estado="Pendiente"
            )

            _notificar_cambio(
                nombre, episodio_limpio, estado_error,
                servidor_fallido, fuente_anterior,
                nombre_servidor_legible(s_alterno["servidor"], s_alterno["enlace"]),
                fuente_anterior, misma_fuente=True
            )
            continue  # Reintenta la descarga con el otro servidor

        # ---- 2) Otra fuente (con todos sus servidores validados) ----
        if fuente_anterior and fuente_anterior.lower() not in [f.lower() for f in lista_excluidas]:
            lista_excluidas.append(fuente_anterior)

        logging.info(
            f"🚫 Fuentes descartadas acumuladas: {', '.join(lista_excluidas)}")

        v_nuevo = buscar_fuente_alternativa(
            driver_servidor, nombre, episodio_limpio, lista_excluidas,
            download_dir, servidores_sin_cuota
        )

        cadena_fallidas = ", ".join(lista_excluidas)

        if v_nuevo is None:
            logging.error(
                "❌ No se encontraron fuentes alternativas válidas. Guardando 'Sin Fuentes'.")
            video["fuentes_fallidas"] = cadena_fallidas

            actualizar_estado_google_sheets(
                sheet_service=sheet_service,
                nombre_hoja="Animes",
                nombre_anime=nombre,
                episodio=episodio_limpio,
                fuentes_fallidas=cadena_fallidas,
                fecha_actualizacion=fecha_ahora,
                nuevo_estado="Sin Fuentes"
            )

            enviar_mensaje_telegram(
                f"⚠️ <b>Alerta: Episodio Sin Fuentes</b>\n\n"
                f"🎬 Anime: <b>{nombre_esc}</b>\n"
                f"📺 Episodio: <b>{episodio_esc}</b>\n"
                f"🔴 Último fallo: <b>{html.escape(servidor_fallido)}</b> ({html.escape(estado_error)})\n"
                f"📝 Fuentes probadas: {html.escape(cadena_fallidas)}\n"
                f"🔴 Estado: <b>Sin Fuentes Disponibles</b>"
            )
            return False

        nueva_fuente = v_nuevo.get("fuente", "Desconocida")
        nuevo_link = v_nuevo.get("link_descarga")
        nuevo_servidor = nombre_servidor_legible(
            v_nuevo.get("servidor_seleccionado"), nuevo_link)

        # A) Actualizar diccionario local en memoria
        video["link_descarga"] = nuevo_link
        video["fuente"] = nueva_fuente
        video["fuentes_fallidas"] = cadena_fallidas
        video["servidor_seleccionado"] = v_nuevo.get("servidor_seleccionado")
        video["servidores_validos"] = v_nuevo.get("servidores_validos", [])

        guardar_servidores_alternos(
            nombre, episodio_limpio, nueva_fuente, video["servidores_validos"])

        logging.info(
            f"✅ Nueva fuente '{nueva_fuente}' ({nuevo_servidor}). Sincronizando Sheets...")

        # B) Sincronizar en Google Sheets
        actualizar_estado_google_sheets(
            sheet_service=sheet_service,
            nombre_hoja="Animes",
            nombre_anime=nombre,
            episodio=episodio_limpio,
            nuevo_enlace=nuevo_link,
            nueva_fuente=nueva_fuente,
            fuentes_fallidas=cadena_fallidas,
            fecha_actualizacion=fecha_ahora,
            nuevo_estado="Pendiente"
        )

        # C) Telegram con el servidor nuevo
        _notificar_cambio(
            nombre, episodio_limpio, estado_error,
            servidor_fallido, fuente_anterior,
            nuevo_servidor, nueva_fuente
        )

        # D) Vuelve al inicio del while: descarga con el nuevo enlace y, si
        #    también falla, repite el ciclo (revisión de "¿sigue fallando?")


def proceso_local_descargar_archivos(download_dir):
    """
    Se conecta a Google Sheets, lee los animes pendientes, y ejecuta
    la descarga local de cada uno, actualizando el servidor al terminar.
    """
    logging.info(
        "\n☁️ Conectando con Google Sheets para leer animes pendientes...")
    sheet_service = obtener_conexion_google_sheets()

    if not sheet_service:
        logging.error("❌ No se pudo conectar con Google Sheets.")
        return

    # 1. Leemos los registros desde tu Google Sheets
    registros_hoja = leer_animes_pendientes(sheet_service)

    if not registros_hoja:
        logging.info("ℹ️ No hay registros en Google Sheets.")
        return

    # 2. Filtramos los que tengan estado "Pendiente"
    videos_finales = [
        {
            "nombre": r.get("nombre"),
            "fuente": r.get("fuente"),
            # Compatibilidad por si tu lógica usa esta llave
            "nombre_anime": r.get("nombre"),
            "episodio_buscado": r.get("episodio"),
            "episodio": r.get("episodio"),
            "link_descarga": r.get("enlace"),
            "estado": r.get("estado"),
            # Historial de fuentes ya descartadas (según cómo lo devuelva tu hoja)
            "fuentes_fallidas": r.get("fuentes_fallidas") or r.get("fuente_fallida") or "",
        }
        for r in registros_hoja
        if r.get("estado", "").lower() in ["pendiente"]
    ]

    if not videos_finales:
        logging.info("🎉 No hay animes pendientes por descargar.")
        return

    logging.info(f"\nAnimes listos para descargar ({len(videos_finales)}):")
    for idx, video in enumerate(videos_finales, 1):
        logging.info(
            f"{idx}. {video.get('nombre')} - Ep: {video.get('episodio_buscado')} [{video.get('estado', 'Desconocido')}]")

    logging.info("\nIniciando descargas automáticamente...")

    driver_servidor = configurar_navegador(download_dir)
    if driver_servidor is None:
        logging.error("❌ No se pudo iniciar el navegador para las descargas.")
        return

    # Servidores (p. ej. 'mega') que se quedaron sin cuota durante ESTA ejecución
    servidores_sin_cuota = set()

    try:
        for video in videos_finales:
            link_descarga = video.get("link_descarga")

            # Si el enlace no existe, lo saltamos
            if not link_descarga or link_descarga == "No encontrado" or video.get("estado") in ["Archivo Caído", "Cuota Agotada"]:
                logging.info(
                    f"⚠️ Saltando {video.get('nombre')}: enlace no disponible o bloqueado.")
                nombre_anime = html.escape(
                    str(video.get("nombre", "Desconocido")))

                enviar_mensaje_telegram(
                    f"⚠️ <b>Alerta de Enlace</b>\n\n"
                    f"🎬 Anime: <b>{nombre_anime}</b>\n"
                    f"🔴 Estado: Archivo Caído o Cuota Agotada."
                )
                continue

            logging.info("\n" + "=" * 60)
            logging.info(
                f"Descargando: {video.get('nombre')} - Episodio {video.get('episodio_buscado')}")
            logging.info("=" * 60)

            procesar_descarga_video(
                video,
                driver_servidor,
                sheet_service,
                download_dir,
                servidores_sin_cuota,
            )

    finally:
        try:
            driver_servidor.quit()
            logging.info("🔒 Driver de servidor cerrado.")
        except Exception:
            pass
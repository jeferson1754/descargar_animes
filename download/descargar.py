import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import os
import logging
import html
import re
import json
from urllib.parse import urlparse

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


# ==========================================
# DETECCIÓN DE VOE (usa dominios que ROTAN con frecuencia)
# ==========================================
#
# VOE redirige a dominios distintos y cambiantes (johnfullwonder, jamesbornmain,
# shannoncoldalready...), así que reconocerlo por una lista fija de palabras
# falla tarde o temprano. La detección combina, en este orden:
#   1) el HOST de la URL (dominios base + dominios aprendidos automáticamente),
#   2) el enlace ORIGINAL / la pista del servidor (voe.sx redirige a un espejo),
#   3) la firma de la PÁGINA (elementos y textos propios de VOE).
# Cuando una descarga por VOE termina bien, su dominio se guarda en
# dominios_voe.json y la próxima vez se reconoce solo por el host.

ARCHIVO_DOMINIOS_VOE = "dominios_voe.json"

# Fragmentos de host de VOE conocidos. Agrega aquí los nuevos si quieres
# (los que descargan bien se aprenden solos en dominios_voe.json).
DOMINIOS_VOE_BASE = (
    "voe.sx",
    "johnfullwonder",
    "jamesbornmain",
    "teresapoliticallearn",
    "shannoncoldalready",
)

# Redirecciones publicitarias conocidas (NO son del servidor)
PATRONES_PUBLICIDAD = (
    "signaldefendgo",
    "clickid=",
    "pets/rabbits",
    "bdsclk",
    "trk=",
    "redirect",
)

_dominios_voe_aprendidos = None  # caché en memoria


def _host_de_url(url):
    """Host en minúsculas, sin puerto ni 'www.' ('' si no se puede leer)."""
    texto = str(url or "").strip().lower()
    if not texto:
        return ""
    if "//" not in texto:
        texto = "//" + texto
    try:
        host = urlparse(texto).netloc.split("@")[-1].split(":")[0]
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def es_url_publicitaria(url):
    url = str(url or "").lower()
    return any(p in url for p in PATRONES_PUBLICIDAD)


def _cargar_dominios_voe_aprendidos():
    global _dominios_voe_aprendidos
    if _dominios_voe_aprendidos is None:
        try:
            with open(ARCHIVO_DOMINIOS_VOE, "r", encoding="utf-8") as f:
                _dominios_voe_aprendidos = set(json.load(f).get("dominios", []))
        except Exception:
            _dominios_voe_aprendidos = set()
    return _dominios_voe_aprendidos


def _host_es_voe(host):
    """True si el host es de VOE: etiqueta 'voe', dominio base o aprendido."""
    if not host:
        return False
    # voe.sx, www.voe.sx, voe-unblock.com ... pero NO 'devoe.com'
    if re.search(r"(^|[.\-])voe([.\-]|$)", host):
        return True
    if any(base in host for base in DOMINIOS_VOE_BASE):
        return True
    return host in _cargar_dominios_voe_aprendidos()


def registrar_dominio_voe(url):
    """Guarda el dominio de una página VOE que sí entregó la descarga."""
    host = _host_de_url(url)
    if not host or _host_es_voe(host) or es_url_publicitaria(url):
        return
    aprendidos = _cargar_dominios_voe_aprendidos()
    aprendidos.add(host)
    try:
        with open(ARCHIVO_DOMINIOS_VOE, "w", encoding="utf-8") as f:
            json.dump({"dominios": sorted(aprendidos)}, f, ensure_ascii=False, indent=4)
        logging.info(f"🧠 Dominio VOE nuevo aprendido: {host}")
    except Exception as e:
        logging.warning(f"⚠️ No se pudo guardar el dominio VOE aprendido: {e}")


def pagina_parece_voe(driver):
    """
    Revisa la página cargada. Devuelve el motivo (str) si parece VOE, o None.
    Firmas fuertes: botón 'a.download-user-file', 'voe' en el título o
    referencias a voe.sx. Firmas débiles: se exigen al menos 2.
    """
    try:
        if driver.find_elements(By.CSS_SELECTOR, "a.download-user-file"):
            return "botón a.download-user-file"

        titulo = (driver.title or "").lower()
        source = (driver.page_source or "").lower()
    except Exception:
        return None

    if re.search(r"\bvoe\b", titulo):
        return "'voe' en el título"
    if re.search(r"voe\.sx|voe-network", source):
        return "referencia a voe.sx en el código"

    debiles = [f for f in ("vplayer", "node_id", "delivery_node") if f in source]
    if len(debiles) >= 2:
        return f"firmas débiles ({', '.join(debiles)})"

    return None


def es_servidor_voe(driver, url):
    """
    Detecta VOE. 'url' puede ser la URL (str) y 'driver' un WebDriver o un str.
    - Con solo texto: se decide por el host (dominios base + aprendidos).
    - Con un WebDriver: si el host no es conocido, se inspecciona la página.
    """
    if _host_es_voe(_host_de_url(url)):
        return True

    if driver is None or isinstance(driver, str):
        return False

    return pagina_parece_voe(driver) is not None


def url_es_del_servidor(url, servidor, hosts_confirmados=()):
    """¿La URL pertenece al servidor ya identificado? (host a host, no por palabra)."""
    if not servidor or servidor == "desconocido":
        return False
    host = _host_de_url(url)
    if host in hosts_confirmados:
        return True
    if servidor == "voe":
        return _host_es_voe(host)
    return nombre_servidor_desde_url(url) == servidor


def detectar_servidor_final(driver, url_final, enlace_original=None, servidor_hint=None):
    """
    Identifica el servidor de la página a la que llegó el navegador.
    Devuelve (servidor, origen), con servidor 'desconocido' si no se pudo.

      1) host de la URL final
      2) VOE por el enlace original / pista (voe.sx redirige a espejos rotativos)
      3) firma de la página (VOE)
    """
    por_url = nombre_servidor_desde_url(url_final)
    if por_url != "desconocido":
        return por_url, "host de la URL"

    # Una redirección publicitaria no cuenta como página de ningún servidor
    if es_url_publicitaria(url_final):
        return "desconocido", "redirección publicitaria"

    pista = (servidor_hint or "").strip().lower()
    if nombre_servidor_desde_url(enlace_original) == "voe" or pista == "voe":
        return "voe", "enlace original / pista (dominio rotativo)"

    motivo = pagina_parece_voe(driver)
    if motivo:
        return "voe", f"firma de la página: {motivo}"

    return "desconocido", "sin coincidencias"


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
                    if es_servidor_voe(href, href) or re.search(r"\bvoe\b", contenido_total):
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
    driver, enlace_descarga, download_dir, nombre_video, fuente, servidor_hint=None
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

        # Detectar el servidor: host de la URL final -> enlace original / pista
        # -> firma de la página (VOE usa dominios rotativos).
        url_final = driver.current_url
        servidor, origen = detectar_servidor_final(
            driver, url_final, enlace_descarga, servidor_hint
        )
        logging.info(
            f"🌐 Servidor final detectado tras redirección: {servidor} "
            f"[{origen}] (URL: {url_final})"
        )

        # Hosts ya confirmados como del servidor (para no confundir un espejo
        # nuevo de VOE con publicidad)
        hosts_confirmados = set()
        if servidor != "desconocido":
            hosts_confirmados.add(_host_de_url(url_final))

        # --------------------------------------------------
        # 2b. Guardián Anti-Redirección Prematura
        # --------------------------------------------------
        # Evita que el JS de la página secuestre la pestaña durante la carga
        # inicial. Compara por HOST (antes buscaba "voe" dentro de la URL y
        # recargaba sin necesidad en los espejos de VOE) y vuelve a detectar
        # el servidor tras cada recarga.
        for reintento in range(3):
            time.sleep(2)
            url_actual = driver.current_url

            if (
                not es_url_publicitaria(url_actual)
                and url_es_del_servidor(url_actual, servidor, hosts_confirmados)
            ):
                break

            logging.warning(
                f"⚠️ Redirección publicitaria o página desconocida ({url_actual[:45]}...). "
                f"Volviendo a cargar enlace ({reintento + 1}/3)..."
            )
            driver.get(enlace_descarga)

            try:
                WebDriverWait(driver, 15).until(
                    lambda d: d.execute_script("return document.readyState")
                    == "complete"
                )
            except Exception:
                pass
            time.sleep(3)

            url_final = driver.current_url
            servidor, origen = detectar_servidor_final(
                driver, url_final, enlace_descarga, servidor_hint
            )
            logging.info(
                f"🌐 Servidor tras recarga: {servidor} [{origen}] (URL: {url_final})"
            )
            if servidor != "desconocido" and not es_url_publicitaria(url_final):
                hosts_confirmados.add(_host_de_url(url_final))

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
            if servidor == "voe":
                registrar_dominio_voe(url_final)
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
                video.get('fuente'),
                servidor_hint=video.get("servidor_seleccionado")
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


def validar_todos_los_servidores(driver, video, servidores_bloqueados=None, servidores_penalizados=None):
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

    # Servidores "penalizados" (p. ej. Mega sin cuota ahora): siguen siendo
    # válidos pero quedan al final, para preferir cualquier otro.
    penalizados = {p.lower() for p in (servidores_penalizados or set())}
    if penalizados:
        validos.sort(key=lambda c: (
            nombre_servidor_desde_url(c["enlace"]) in penalizados
            or str(c["servidor"]).lower() in penalizados))

    video["servidores_validos"] = validos

    if not validos:
        logging.error(
            f"❌ Ningún servidor disponible en la fuente '{fuente}'.")
        return False

    video["link_descarga"] = validos[0]["enlace"]
    video["servidor_seleccionado"] = validos[0]["servidor"]
    return True


def evaluar_video_de_fuente(driver, video, nombre_esperado, episodio_esperado, servidores_bloqueados=None,
                            servidores_penalizados=None):
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

    if validar_todos_los_servidores(driver, video, servidores_bloqueados, servidores_penalizados):
        return True, "ok"

    return False, "ningún servidor disponible"


# ==========================================
# ESCRITURA SEGURA EN SHEETS + MEMORIA DE FUENTES FALLIDAS
# ==========================================

ARCHIVO_FUENTES_FALLIDAS = "fuentes_fallidas.json"
FUENTES_FALLIDAS_TTL_HORAS = 24   # pasado este tiempo, una fuente fallida se vuelve a probar


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def actualizar_sheet(**kwargs):
    """
    Envoltorio de actualizar_estado_google_sheets:
      - la fecha SIEMPRE viaja como texto 'YYYY-MM-DD HH:MM:SS' (si no se pasó, se pone la actual),
      - nunca se envía un booleano como valor de celda (un True se vería como "TRUE"),
      - deja en el log exactamente lo que se envía a la hoja.
    """
    kwargs.setdefault("nombre_hoja", "Animes")

    # Un parámetro en None equivale a "no enviarlo" (como antes)
    for clave in [k for k, v in kwargs.items() if v is None]:
        del kwargs[clave]

    fecha = kwargs.get("fecha_actualizacion")
    if not isinstance(fecha, str) or not fecha.strip():
        kwargs["fecha_actualizacion"] = _ahora()

    for clave, valor in list(kwargs.items()):
        if clave in ("sheet_service", "nombre_hoja", "crear_si_no_existe"):
            continue
        if isinstance(valor, bool):
            logging.warning(
                f"⚠️ Se descartó un booleano en '{clave}' para no escribir TRUE/FALSE en la hoja.")
            del kwargs[clave]
        elif clave in ("nuevo_enlace", "nueva_fuente", "fuentes_fallidas", "nuevo_estado") \
                and valor is not None and not isinstance(valor, str):
            kwargs[clave] = str(valor)

    enviado = ", ".join(
        f"{k}={v!r}" for k, v in kwargs.items() if k != "sheet_service")
    logging.info(f"📝 Sheets ← {enviado}")

    return actualizar_estado_google_sheets(**kwargs)


def _unir_fuentes(*listas):
    """Une listas (o cadenas 'A, B') de fuentes sin repetir (ignora mayúsculas), conservando el orden."""
    vistos, resultado = set(), []
    for lista in listas:
        if isinstance(lista, str):
            lista = lista.split(",")
        for f in lista or []:
            f = str(f).strip()
            if f and f.lower() not in vistos:
                vistos.add(f.lower())
                resultado.append(f)
    return resultado


def _leer_json_fuentes():
    try:
        if os.path.exists(ARCHIVO_FUENTES_FALLIDAS):
            with open(ARCHIVO_FUENTES_FALLIDAS, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logging.warning(f"⚠️ No se pudo leer {ARCHIVO_FUENTES_FALLIDAS}: {e}")
    return {}


def _escribir_json_fuentes(datos):
    try:
        with open(ARCHIVO_FUENTES_FALLIDAS, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.warning(f"⚠️ No se pudo guardar {ARCHIVO_FUENTES_FALLIDAS}: {e}")


def cargar_fuentes_fallidas(nombre, episodio):
    """
    Fuentes que ya fallaron para ESTE episodio. Se guardan en disco además de
    en Sheets para no depender de cómo se lea esa columna y así no volver a
    una fuente que ya falló (rebote A -> B -> A).
    """
    registro = _leer_json_fuentes().get(_clave_episodio(nombre, episodio))
    if not registro:
        return []
    try:
        antiguedad = datetime.now() - datetime.strptime(
            registro.get("actualizado", ""), "%Y-%m-%d %H:%M:%S")
        if antiguedad.total_seconds() > FUENTES_FALLIDAS_TTL_HORAS * 3600:
            return []
    except Exception:
        pass
    return registro.get("fuentes", [])


def guardar_fuentes_fallidas(nombre, episodio, fuentes):
    datos = _leer_json_fuentes()
    datos[_clave_episodio(nombre, episodio)] = {
        "fuentes": _unir_fuentes(fuentes),
        "actualizado": _ahora(),
    }
    _escribir_json_fuentes(datos)


def borrar_fuentes_fallidas(nombre, episodio):
    datos = _leer_json_fuentes()
    if datos.pop(_clave_episodio(nombre, episodio), None) is not None:
        _escribir_json_fuentes(datos)


def _acumular_bitacora(bitacora, entradas):
    """Agrega (fuente, estado) a la bitácora; el estado más informativo gana sobre 'excluida'."""
    for fuente, estado in entradas or []:
        existente = next((i for i, (f, _) in enumerate(bitacora) if f.lower() == str(fuente).lower()), None)
        if existente is None:
            bitacora.append((str(fuente), str(estado)))
        elif not str(estado).startswith("excluida"):
            bitacora[existente] = (str(fuente), str(estado))


def resumen_fuentes_html(bitacora):
    """Texto para Telegram con TODAS las fuentes consultadas y qué pasó con cada una."""
    if not bitacora:
        return ""
    lineas = [f"• {html.escape(str(f))}: {html.escape(str(e))}" for f, e in bitacora]
    return "🔎 <b>Fuentes consultadas:</b>\n" + "\n".join(lineas) + "\n"


# ==========================================
# ESTADO COMPARTIDO DE SERVIDORES (CUOTA) Y RESUMEN DE LA NUBE
# ==========================================
#
# La cuota de transferencia de Mega es de la IP que DESCARGA, y solo se puede
# comprobar de verdad al pulsar "Descargar". La fase local la detecta y la
# anota aquí; la fase nube la consulta para no dejar como "válido" un enlace de
# Mega que ahora mismo no se puede bajar (y para preferir otro servidor).
# Si ambas fases corren en máquinas distintas, este archivo debe compartirse.

ARCHIVO_ESTADO_SERVIDORES = "estado_servidores.json"
CUOTA_SERVIDOR_HORAS = 6          # cuánto se considera "sin cuota" tras detectarlo
ENVIAR_RESUMEN_NUBE = True        # pon False si base_excel ya envía un resumen propio


def marcar_servidor_sin_cuota(servidor):
    """Anota que un servidor ('mega') se quedó sin cuota AHORA (detectado al descargar)."""
    try:
        datos = {}
        if os.path.exists(ARCHIVO_ESTADO_SERVIDORES):
            with open(ARCHIVO_ESTADO_SERVIDORES, "r", encoding="utf-8") as f:
                datos = json.load(f)
        datos[servidor] = _ahora()
        with open(ARCHIVO_ESTADO_SERVIDORES, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.warning(f"⚠️ No se pudo guardar el estado de cuota de {servidor}: {e}")


def servidores_sin_cuota_vigentes():
    """Servidores marcados sin cuota hace menos de CUOTA_SERVIDOR_HORAS."""
    vigentes = set()
    try:
        if not os.path.exists(ARCHIVO_ESTADO_SERVIDORES):
            return vigentes
        with open(ARCHIVO_ESTADO_SERVIDORES, "r", encoding="utf-8") as f:
            datos = json.load(f)
        for servidor, marca in datos.items():
            try:
                horas = (datetime.now() - datetime.strptime(
                    marca, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
                if horas < CUOTA_SERVIDOR_HORAS:
                    vigentes.add(servidor)
            except Exception:
                continue
    except Exception as e:
        logging.warning(f"⚠️ No se pudo leer el estado de cuota: {e}")
    return vigentes


def _anotar(resumen, clave, nombre, episodio, **datos):
    """Registra un hecho para el resumen final de la nube."""
    if resumen is None:
        return
    resumen.setdefault(clave, []).append(
        {"nombre": nombre, "episodio": episodio, **datos})


def _texto_resumen_nube(resumen, maximo):
    e = lambda x: html.escape(str(x if x is not None else ""))
    base = lambda i: f"• <b>{e(i['nombre'])}</b> — Ep. {e(i['episodio'])}"

    def lista(items, extra=None):
        lineas = [base(i) + (extra(i) if extra else "") for i in items[:maximo]]
        if len(items) > maximo:
            lineas.append(f"… y {len(items) - maximo} más")
        return "\n".join(lineas)

    secciones = []

    def seccion(titulo, clave, extra=None):
        items = resumen.get(clave) or []
        if items:
            secciones.append(f"{titulo} ({len(items)})\n{lista(items, extra)}")

    seccion("✅ <b>Listos para descargar</b>", "nuevos",
            lambda i: f" · {e(i.get('servidor'))} ({e(i.get('fuente'))})"
            + (f" ↩ tras descartar {e(i['descartadas'])}" if i.get("descartadas") else ""))
    seccion("🔁 <b>Enlaces revalidados (siguen válidos)</b>", "revalidados",
            lambda i: f" · {e(i.get('servidor'))} ({e(i.get('fuente'))})")
    seccion("🔄 <b>Enlaces cambiados</b>", "cambiados",
            lambda i: f": {e(i.get('antes'))} → <b>{e(i.get('ahora'))}</b> ({e(i.get('fuente'))}) · {e(i.get('motivo'))}")
    seccion("⏳ <b>En espera de cuota</b>", "esperando_cuota",
            lambda i: f" · {e(i.get('servidor'))} ({e(i.get('fuente'))})")
    seccion("🚨 <b>Sin fuentes</b>", "sin_fuentes",
            lambda i: f" · probadas: {e(i.get('fuentes'))}" if i.get("fuentes") else "")
    seccion("🔍 <b>Aún no encontrados</b>", "no_encontrados")

    if not secciones:
        return ""
    return "☁️ <b>Resumen de la nube</b>\n\n" + "\n\n".join(secciones)


def enviar_resumen_nube(resumen):
    """Mensaje final de Telegram con todo lo que hizo la nube en este ciclo."""
    if not ENVIAR_RESUMEN_NUBE:
        return
    for maximo in (8, 4, 2):          # Telegram admite ~4096 caracteres
        texto = _texto_resumen_nube(resumen, maximo)
        if len(texto) <= 3900:
            break
    if texto:
        enviar_mensaje_telegram(texto)


def buscar_fuente_alternativa(driver, nombre, episodio, lista_excluidas, download_dir,
                              servidores_bloqueados=None, bitacora=None,
                              servidores_penalizados=None, persistir=True):
    """
    Recorre las fuentes restantes hasta encontrar una que:
      - devuelva el anime/temporada/episodio correcto, y
      - tenga al menos un servidor disponible.
    Modifica 'lista_excluidas' agregando cada fuente descartada (y la guarda en
    disco). 'bitacora' (lista) recibe (fuente, qué pasó) de TODAS las fuentes
    consultadas, para poder mostrar cuáles se probaron realmente.
    Devuelve el video válido o None si se agotaron las fuentes.
    """
    if bitacora is None:
        bitacora = []

    while True:
        logging.info(
            f"🚫 Fuentes descartadas: {', '.join(lista_excluidas) or 'ninguna'}")

        encontrados = buscar_en_fuentes(
            [{"nombre": nombre, "episodio_buscado": episodio}],
            FUENTES_ANIME,
            excluir_fuente=lista_excluidas,
            download_dir=download_dir,
        )

        _acumular_bitacora(
            bitacora, getattr(buscar_en_fuentes, "ultimo_resumen", []))

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
                driver, v_alt, nombre, episodio, servidores_bloqueados,
                servidores_penalizados)

            if valido:
                logging.info(
                    f"✅ Fuente alternativa '{fuente_alt}' válida "
                    f"({v_alt.get('servidor_seleccionado')}) para: {nombre}"
                )
                _acumular_bitacora(bitacora, [(fuente_alt, "válida")])
                return v_alt

            logging.error(f"❌ Fuente '{fuente_alt}' descartada: {motivo}")
            lista_excluidas.append(fuente_alt)
            excluidas_lower.add(str(fuente_alt).lower())
            if persistir:
                guardar_fuentes_fallidas(nombre, episodio, lista_excluidas)
            _acumular_bitacora(bitacora, [(fuente_alt, f"descartada: {motivo}")])

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


def _servidor_desde_cache(nombre, episodio, fuente, enlace):
    """Nombre del servidor ('Mega', 'VOE'...) de un enlace ya validado en la fase nube."""
    for srv in cargar_servidores_alternos(nombre, episodio, fuente, {enlace}):
        if srv.get("enlace") == enlace:
            return srv.get("servidor")
    return None


def cargar_servidores_alternos(nombre, episodio, fuente, enlaces_conocidos=None):
    """
    Servidores de la MISMA fuente para ese episodio.
    Se aceptan si coincide la fuente O si alguno de los 'enlaces_conocidos'
    (p. ej. el enlace que está fallando) figura en la lista guardada; así no
    depende de que la fila de Sheets traiga bien escrito el nombre de la fuente.
    """
    try:
        if not os.path.exists(ARCHIVO_SERVIDORES_ALTERNOS):
            return []
        with open(ARCHIVO_SERVIDORES_ALTERNOS, "r", encoding="utf-8") as f:
            datos = json.load(f)

        registro = datos.get(_clave_episodio(nombre, episodio))
        if not registro:
            return []

        servidores = registro.get("servidores", [])
        coincide_fuente = (
            str(registro.get("fuente", "")).lower() == str(fuente or "").lower())
        enlaces_guardados = {srv.get("enlace") for srv in servidores}
        coincide_enlace = any(
            e in enlaces_guardados for e in (enlaces_conocidos or []) if e)

        if not (coincide_fuente or coincide_enlace):
            return []
        return servidores

    except Exception as e:
        logging.warning(f"⚠️ No se pudieron leer servidores alternos: {e}")
        return []


def refrescar_servidores_de_fuente(nombre, episodio, fuente, download_dir):
    """
    Si no hay servidores alternos guardados (enlace registrado por una versión
    anterior, o la fase nube corre en otra máquina), vuelve a consultar SOLO esa
    fuente para recuperar todos sus servidores. Se validan uno a uno al usarlos.
    """
    otras = [str(f.get("nombre")) for f in FUENTES_ANIME
             if f.get("nombre") and str(f["nombre"]).lower() != str(fuente).lower()]
    try:
        encontrados = buscar_en_fuentes(
            [{"nombre": nombre, "episodio_buscado": episodio}],
            FUENTES_ANIME,
            excluir_fuente=otras,
            download_dir=download_dir,
        )
    except Exception as e:
        logging.warning(f"⚠️ No se pudo refrescar los servidores de '{fuente}': {e}")
        return []

    for v in encontrados:
        if str(v.get("fuente", "")).lower() != str(fuente).lower():
            continue
        candidatos = recopilar_servidores_candidatos(v)
        if candidatos:
            guardar_servidores_alternos(nombre, episodio, fuente, candidatos)
            return candidatos
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


ESTADOS_FINALES = {"COMPLETADO", "DESCARGADO"}
ESTADOS_REVALIDAR = {"PENDIENTE", "CUOTA AGOTADA"}
ESTADOS_REBUSCAR = {"CAMBIAR FUENTE", "SIN FUENTES", "ARCHIVO CAÍDO", "ARCHIVO CAIDO"}


def _ep_limpio(ep):
    return int(ep) if str(ep).strip().isdigit() else ep


def revalidar_registro_en_sheets(driver, sheet_service, registro, download_dir, sin_cuota, resumen):
    """
    Un episodio que YA está en Sheets como Pendiente: se valida su enlace.

      1) Enlace sano                      -> se deja tal cual.
      2) Archivo caído / sin enlace       -> otro servidor de la MISMA fuente;
                                             si no hay, otra fuente (con todos sus servidores validados).
      3) Mega sin cuota (temporal)        -> igual, pero si no hay alternativa queda Pendiente
                                             (no se marca la fuente como fallida).

    Devuelve: 'ok' | 'cambio_servidor' | 'cambio_fuente' | 'esperando_cuota' | 'sin_fuentes'.
    """
    nombre = registro.get("nombre")
    episodio = _ep_limpio(registro.get("episodio"))
    link = registro.get("enlace")
    fuente = registro.get("fuente") or "Desconocida"
    estado_hoja = str(registro.get("estado", "")).strip()

    fallidas = _unir_fuentes(
        registro.get("fuentes_fallidas") or registro.get("fuente_fallida"),
        cargar_fuentes_fallidas(nombre, episodio),
    )

    servidor_key = nombre_servidor_desde_url(link)
    servidor_txt = nombre_servidor_legible(None, link)
    fecha = _ahora()

    # ---------------- 1. ¿cómo está el enlace? ----------------
    if not link or link == "No encontrado":
        motivo = "Sin enlace"
    elif not validar_servidor(driver, servidor_key, link):
        motivo = "Archivo Caído"
    elif servidor_key in sin_cuota:
        motivo = "Cuota Agotada"
    else:
        motivo = None

    if motivo is None:
        logging.info(f"✅ Enlace vigente ({servidor_txt}) para {nombre} Ep {episodio}.")
        if estado_hoja.upper() != "PENDIENTE":
            actualizar_sheet(
                sheet_service=sheet_service, nombre_anime=nombre, episodio=episodio,
                nuevo_estado="Pendiente", fecha_actualizacion=fecha)
        _anotar(resumen, "revalidados", nombre, episodio, servidor=servidor_txt, fuente=fuente)
        return "ok"

    logging.warning(f"⚠️ {motivo} en {servidor_txt} ({fuente}) para {nombre} Ep {episodio}. Buscando reemplazo...")

    # ---------------- 2. otro servidor de la MISMA fuente ----------------
    temporal = (motivo == "Cuota Agotada")
    ref = {"fuente": fuente, "link_descarga": link}

    # Se prefiere un servidor sin problemas de cuota...
    s_alt = _siguiente_servidor_misma_fuente(
        driver, ref, nombre, episodio, {link}, sin_cuota, download_dir)
    # ...pero si el enlace está CAÍDO de verdad, un Mega con cuota agotada (temporal)
    # sigue siendo mejor que nada: se acepta y el episodio espera a que haya cuota.
    if not s_alt and not temporal:
        s_alt = _siguiente_servidor_misma_fuente(
            driver, ref, nombre, episodio, {link}, set(), download_dir)

    if s_alt:
        actualizar_sheet(
            sheet_service=sheet_service, nombre_anime=nombre, episodio=episodio,
            nuevo_enlace=s_alt["enlace"], nueva_fuente=fuente,
            fuentes_fallidas=", ".join(fallidas) or None,
            nuevo_estado="Pendiente", fecha_actualizacion=fecha)
        nuevo_srv = nombre_servidor_legible(s_alt.get("servidor"), s_alt["enlace"])
        _notificar_cambio(nombre, episodio, motivo, servidor_txt, fuente, nuevo_srv, fuente, misma_fuente=True)
        _anotar(resumen, "cambiados", nombre, episodio,
                antes=servidor_txt, ahora=nuevo_srv, fuente=fuente, motivo=motivo)
        return "cambio_servidor"

    # ---------------- 3. otra fuente ----------------
    temporal = (motivo == "Cuota Agotada")
    excluidas = _unir_fuentes(fallidas, [fuente])
    if not temporal:
        guardar_fuentes_fallidas(nombre, episodio, excluidas)
    bitacora = [(fuente, f"falló: {motivo}")]

    v = buscar_fuente_alternativa(
        driver, nombre, episodio, excluidas, download_dir,
        # Enlace caído: Mega sin cuota solo se penaliza (queda al final), no se descarta.
        # Cuota agotada: se busca explícitamente algo que NO sea ese servidor.
        servidores_bloqueados=sin_cuota if temporal else None,
        servidores_penalizados=sin_cuota,
        bitacora=bitacora, persistir=not temporal)

    if v:
        v["estado"] = "Pendiente"
        v["fuentes_fallidas"] = ", ".join(fallidas if temporal else excluidas)
        _registrar_video_valido(
            sheet_service, v, nombre, episodio, fecha,
            fuentes_fallidas=v["fuentes_fallidas"], prefijo_captura="Link Alterno ")
        nuevo_srv = nombre_servidor_legible(v.get("servidor_seleccionado"), v.get("link_descarga"))
        _notificar_cambio(nombre, episodio, motivo, servidor_txt, fuente, nuevo_srv, v.get("fuente"))
        _anotar(resumen, "cambiados", nombre, episodio,
                antes=servidor_txt, ahora=nuevo_srv, fuente=v.get("fuente"), motivo=motivo)
        return "cambio_fuente"

    if temporal:
        logging.warning(f"⏳ {servidor_txt} sin cuota y sin alternativas para {nombre} Ep {episodio}: se deja Pendiente.")
        if estado_hoja.upper() != "PENDIENTE":
            actualizar_sheet(
                sheet_service=sheet_service, nombre_anime=nombre, episodio=episodio,
                nuevo_estado="Pendiente", fecha_actualizacion=fecha)
        _anotar(resumen, "esperando_cuota", nombre, episodio, servidor=servidor_txt, fuente=fuente)
        return "esperando_cuota"

    # Sin alternativas y el enlace está caído de verdad
    cadena = ", ".join(excluidas)
    actualizar_sheet(
        sheet_service=sheet_service, nombre_anime=nombre, episodio=episodio,
        fuentes_fallidas=cadena, nuevo_estado="Sin Fuentes", fecha_actualizacion=fecha)
    enviar_mensaje_telegram(
        f"🚨 <b>Alerta:</b> Se agotaron todas las fuentes para: "
        f"<b>{html.escape(str(nombre))} Episodio {html.escape(str(episodio))}</b>\n"
        f"📝 Fuentes probadas: {html.escape(cadena)}\n"
        f"{resumen_fuentes_html(bitacora)}"
        "⏱️ Marcado como 'Sin Fuentes'. Se reintentará en el próximo ciclo."
    )
    _anotar(resumen, "sin_fuentes", nombre, episodio, fuentes=cadena)
    return "sin_fuentes"


def flujo_descarga_animes(file_name, download_dir):
    """
    Flujo de la nube:
      1) Saca TODOS los episodios pendientes.
      2) Los cruza con Google Sheets:
           - Completado               -> se omite.
           - Ya está como Pendiente   -> se VALIDA su enlace (archivo caído / cuota de Mega);
                                         si falla, se busca reemplazo.
           - Cambiar Fuente / Sin Fuentes -> se vuelve a buscar (excluyendo las fuentes fallidas).
           - No está                  -> se busca en las fuentes y se valida el enlace.
      3) Resumen final por Telegram.
    """
    resumen = {}

    # ---------------------------------------------------------------
    # 1. Todos los pendientes
    # ---------------------------------------------------------------
    datos_crudos = leer_nombres_desde_txt(file_name)

    if not datos_crudos:
        logging.error("❌ No hay animes pendientes para buscar.")
        return False

    animes_a_expandir = []

    for item in datos_crudos:
        nombre = item.get("nombre")
        episodio_actual = item.get("episodio_actual", 0)
        pendientes = item.get("pendientes", 0)

        if pendientes > 0:
            for i in range(1, pendientes + 1):
                animes_a_expandir.append({
                    "nombre": nombre,
                    "episodio_buscado": episodio_actual + i
                })
        else:
            animes_a_expandir.append(item)

    if not animes_a_expandir:
        logging.error("❌ No hay episodios pendientes para procesar.")
        return False

    # ---------------------------------------------------------------
    # 2. Cruce con Google Sheets
    # ---------------------------------------------------------------
    logging.info("☁️ Conectando con Google Sheets para verificar el historial previo...")
    sheet_service = obtener_conexion_google_sheets()

    # ⚠️ Debe devolver TODAS las filas (incluidas las 'Completado')
    animes_en_sheet = leer_animes_pendientes(sheet_service) if sheet_service else []

    nuevos, a_revalidar, a_rebuscar = [], [], []

    for anime_obj in animes_a_expandir:
        nombre_obj = str(anime_obj.get("nombre", "")).strip().lower()
        ep_obj = str(anime_obj.get("episodio_buscado", "")).strip()

        registro = next(
            (a for a in animes_en_sheet
             if str(a["nombre"]).strip().lower() == nombre_obj
             and str(a["episodio"]).strip() == ep_obj),
            None
        )

        if not registro:
            anime_obj["_estado_hoja"] = ""
            nuevos.append(anime_obj)
            continue

        estado = str(registro.get("estado", "")).strip().upper()

        if estado in ESTADOS_FINALES:
            logging.info(
                f"⏩ Omitiendo '{anime_obj.get('nombre')}' (Ep. {ep_obj}): ya está '{registro.get('estado')}' en Google Sheets.")
        elif estado in ESTADOS_REVALIDAR:
            a_revalidar.append(registro)
        elif estado in ESTADOS_REBUSCAR:
            anime_obj["_estado_hoja"] = estado
            if estado == "SIN FUENTES":
                # Se reintenta con todas las fuentes (puede haber salido el episodio)
                anime_obj["fuente_fallida"] = ""
                borrar_fuentes_fallidas(anime_obj.get("nombre"), anime_obj.get("episodio_buscado"))
            else:
                anime_obj["fuente_fallida"] = (
                    registro.get("fuentes_fallidas") or registro.get("fuente_fallida") or "")
            a_rebuscar.append(anime_obj)
        else:
            logging.info(
                f"⏩ Omitiendo '{anime_obj.get('nombre')}' (Ep. {ep_obj}): estado '{registro.get('estado')}' no gestionado.")

    if not (nuevos or a_revalidar or a_rebuscar):
        logging.info("✅ Todos los episodios pendientes ya estaban descargados en Google Sheets.")
        enviar_mensaje_telegram(
            "✅ <b>Animes al día</b>\nTodos los episodios pendientes ya se encuentran descargados.")
        return False

    sin_cuota = servidores_sin_cuota_vigentes()
    if sin_cuota:
        logging.info(f"⏳ Servidores sin cuota (vigente): {', '.join(sorted(sin_cuota))}")

    # ---------------------------------------------------------------
    # 2b. Los que YA están como Pendiente: validar el enlace
    # ---------------------------------------------------------------
    if a_revalidar:
        logging.info(f"🔁 Revalidando enlaces de {len(a_revalidar)} episodio(s) ya registrado(s)...")
        driver = configurar_navegador(download_dir)

        if driver is None:
            logging.error("❌ No se pudo iniciar el navegador para revalidar los enlaces.")
        else:
            try:
                for registro in a_revalidar:
                    try:
                        revalidar_registro_en_sheets(
                            driver, sheet_service, registro, download_dir, sin_cuota, resumen)
                    except Exception as e:
                        logging.error(
                            f"❌ Error revalidando {registro.get('nombre')} Ep {registro.get('episodio')}: {e}")
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

    # ---------------------------------------------------------------
    # 3. Los nuevos (y los de 'Cambiar Fuente' / 'Sin Fuentes'): buscar en las fuentes
    # ---------------------------------------------------------------
    por_buscar = nuevos + a_rebuscar
    videos_encontrados = []

    if por_buscar:
        logging.info(f"Buscando {len(por_buscar)} episodio(s) en las fuentes...")

    for anime_obj in por_buscar:
        nombre_a = anime_obj.get("nombre")
        ep_a = anime_obj.get("episodio_buscado", anime_obj.get("episodio_actual"))

        # Se excluyen las fuentes que ya fallaron para ESTE episodio
        previas = _unir_fuentes(
            anime_obj.get("fuente_fallida"),
            cargar_fuentes_fallidas(nombre_a, ep_a),
        )

        encontrados_anime = buscar_en_fuentes(
            [anime_obj],
            FUENTES_ANIME,
            excluir_fuente=previas or None,
            download_dir=download_dir
        )

        for v in encontrados_anime:
            v["fuentes_fallidas"] = ", ".join(previas)

        videos_encontrados.extend(encontrados_anime)

        if not encontrados_anime:
            estado_hoja = anime_obj.get("_estado_hoja", "")
            if estado_hoja == "CAMBIAR FUENTE":
                # Ya había una fuente fallida y no hay ninguna otra con el episodio
                cadena = ", ".join(previas)
                if sheet_service:
                    actualizar_sheet(
                        sheet_service=sheet_service, nombre_anime=nombre_a, episodio=_ep_limpio(ep_a),
                        fuentes_fallidas=cadena or None, nuevo_estado="Sin Fuentes",
                        fecha_actualizacion=_ahora())
                _anotar(resumen, "sin_fuentes", nombre_a, ep_a, fuentes=cadena)
            elif estado_hoja == "":
                _anotar(resumen, "no_encontrados", nombre_a, ep_a)

    with open("videos_encontrados.txt", "w", encoding="utf-8") as archivo_txt:
        json.dump(videos_encontrados, archivo_txt, ensure_ascii=False, indent=4)

    # ---------------------------------------------------------------
    # 4. Validar los enlaces de lo encontrado y registrarlo en Sheets
    # ---------------------------------------------------------------
    videos_validos = []
    if videos_encontrados:
        resultado = proceso_nube_buscar_y_guardar_sheets(
            download_dir, videos_encontrados, resumen=resumen)
        videos_validos = resultado or []
    else:
        logging.info("No se encontraron videos nuevos para los animes indicados.")

    # ---------------------------------------------------------------
    # 5. Resumen por Telegram
    # ---------------------------------------------------------------
    enviar_resumen_nube(resumen)

    return videos_validos


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
        actualizar_sheet(**kwargs)


def proceso_nube_buscar_y_guardar_sheets(download_dir, videos_encontrados, resetear_fuentes_previas=False,
                                         resumen=None):
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
    sin_cuota_nube = servidores_sin_cuota_vigentes()   # Mega sin cuota ahora -> se prefiere otro servidor

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
                driver, video, nombre_servidor, episodio_limpio,
                servidores_penalizados=sin_cuota_nube)

            if valido:
                logging.info(
                    f"✅ Enlace válido ({video.get('servidor_seleccionado')}) para: {nombre_servidor}")
                video["estado"] = "Pendiente"

                _registrar_video_valido(
                    sheet_service, video, nombre_servidor, episodio_limpio,
                    fecha_ahora,
                    fuentes_fallidas=video.get("fuentes_fallidas"),
                    prefijo_captura="Link_"
                )

                _anotar(resumen, "nuevos", nombre_servidor, episodio_limpio,
                        servidor=nombre_servidor_legible(
                            video.get("servidor_seleccionado"), video.get("link_descarga")),
                        fuente=video.get("fuente"),
                        descartadas=video.get("fuentes_fallidas", ""))
                videos_finales.append(video)
                continue

            # --- CASO B: la fuente principal falló -> Re-búsqueda en cascada ---
            logging.error(
                f"❌ Fuente inicial descartada para {nombre_servidor} ({motivo}). Buscando fuentes alternativas...")

            if resetear_fuentes_previas:
                lista_excluidas = []
                borrar_fuentes_fallidas(nombre_servidor, episodio_limpio)
            else:
                # Lo que traiga el video (leído de Sheets) + lo guardado en disco
                lista_excluidas = _unir_fuentes(
                    video.get("fuentes_fallidas", ""),
                    cargar_fuentes_fallidas(nombre_servidor, episodio_limpio),
                )

            fuente_actual = video.get("fuente", "Desconocida")
            lista_excluidas = _unir_fuentes(lista_excluidas, [fuente_actual])
            guardar_fuentes_fallidas(nombre_servidor, episodio_limpio, lista_excluidas)

            bitacora = [(fuente_actual, f"descartada: {motivo}")]

            v_alt = buscar_fuente_alternativa(
                driver, nombre_servidor, episodio_limpio, lista_excluidas,
                download_dir, bitacora=bitacora,
                servidores_penalizados=sin_cuota_nube
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

                _anotar(resumen, "nuevos", nombre_servidor, episodio_limpio,
                        servidor=nombre_servidor_legible(
                            v_alt.get("servidor_seleccionado"), v_alt.get("link_descarga")),
                        fuente=v_alt.get("fuente"),
                        descartadas=v_alt.get("fuentes_fallidas", ""))
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
                f"{resumen_fuentes_html(bitacora)}"
                "⏱️ Marcado como 'Sin Fuentes'. Se reintentará en el próximo ciclo."
            )
            logging.error(msg_error)
            enviar_mensaje_telegram(msg_error)

            video["estado"] = "Sin Fuentes"
            video["fuentes_fallidas"] = cadena_final_fallidas

            if sheet_service:
                actualizar_sheet(
                    sheet_service=sheet_service,
                    nombre_hoja="Animes",
                    nombre_anime=nombre_servidor,
                    episodio=episodio_limpio,
                    fuentes_fallidas=cadena_final_fallidas,
                    nuevo_estado="Sin Fuentes",
                    fecha_actualizacion=fecha_ahora,
                    crear_si_no_existe=True
                )

            _anotar(resumen, "sin_fuentes", nombre_servidor, episodio_limpio,
                    fuentes=cadena_final_fallidas)
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


def _siguiente_servidor_misma_fuente(driver, video, nombre, episodio, enlaces_fallidos, servidores_bloqueados,
                                     download_dir=None):
    """
    Busca, entre los servidores de la MISMA fuente, uno que no haya fallado
    todavía (lo vuelve a validar porque pudo caerse mientras tanto).

    Los servidores salen de la caché de la fase nube; si ya no queda ninguno
    sin probar (o no hay caché), se vuelve a consultar esa fuente una vez.
    """
    fuente = video.get("fuente") or "Desconocida"
    bloqueados = {b.lower() for b in servidores_bloqueados}
    conocidos = set(enlaces_fallidos) | {video.get("link_descarga")}

    candidatos = cargar_servidores_alternos(nombre, episodio, fuente, conocidos)
    sin_probar = [c for c in candidatos
                  if c.get("enlace") and c["enlace"] not in enlaces_fallidos]

    if (not sin_probar and download_dir and fuente != "Desconocida"
            and not video.get("_servidores_refrescados")):
        video["_servidores_refrescados"] = True
        logging.info(
            f"🔄 Sin servidores alternos guardados para '{fuente}': consultando de nuevo esa fuente...")
        candidatos = refrescar_servidores_de_fuente(nombre, episodio, fuente, download_dir)

    for s in candidatos:
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
    Descarga un episodio. Si el servidor falla (archivo caído, cuota agotada o
    descarga fallida tras los 3 intentos):
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

    # Fuentes ya fallidas: lo que trae la fila de Sheets + lo guardado en disco
    lista_excluidas = _unir_fuentes(
        video.get("fuentes_fallidas", ""),
        cargar_fuentes_fallidas(nombre, episodio_limpio),
    )
    enlaces_fallidos = set()
    cambios = 0

    while True:
        fecha_ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # La fase local lee el enlace desde Sheets (sin nombre de servidor):
        # se recupera de la caché de la fase nube para dar la pista (p. ej. VOE)
        if not video.get("servidor_seleccionado"):
            video["servidor_seleccionado"] = _servidor_desde_cache(
                nombre, episodio_limpio, video.get("fuente"), video.get("link_descarga")
            )

        servidor_actual = nombre_servidor_desde_url(video.get("link_descarga"))

        # Si Mega ya se quedó sin cuota en esta ejecución, ni lo intentamos
        omitido_por_cuota = False
        if servidor_actual in servidores_sin_cuota:
            logging.warning(
                f"⏭️ '{servidor_actual}' sin cuota. Se omite la descarga directa.")
            resultado = "cuota_agotada"
            omitido_por_cuota = True
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
                actualizar_sheet(
                    sheet_service=sheet_service,
                    nombre_hoja="Animes",
                    nombre_anime=nombre,
                    episodio=episodio,
                    nuevo_estado="Completado",
                    fuentes_fallidas=", ".join(lista_excluidas) if lista_excluidas else None
                )

                marcar_anime_descargado_con_selenium(
                    driver_servidor, nombre, episodio)

            borrar_fuentes_fallidas(nombre, episodio_limpio)
            return True

        # ---------------------------------------------------------------------
        # OPCIÓN B: Falla del servidor actual (archivo caído, cuota agotada o
        # descarga fallida tras los 3 intentos: timeout, botón no encontrado...)
        # -> siguiente servidor de la MISMA fuente -> si no hay, otra fuente.
        # ---------------------------------------------------------------------
        if resultado == "archivo_caido":
            estado_error = "Archivo Caído"
        elif resultado == "cuota_agotada":
            estado_error = "Cuota Agotada"
        else:
            estado_error = "Descarga Fallida (3 intentos)"

        enlace_fallido = video.get("link_descarga")
        servidor_fallido = nombre_servidor_legible(
            video.get("servidor_seleccionado"), enlace_fallido)
        fuente_anterior = video.get("fuente") or "Desconocida"

        enlaces_fallidos.add(enlace_fallido)

        if resultado == "cuota_agotada":
            clave = nombre_servidor_desde_url(enlace_fallido)
            if clave != "desconocido":
                servidores_sin_cuota.add(clave)
                if not omitido_por_cuota:      # solo si la cuota se detectó AHORA, no al saltarla
                    marcar_servidor_sin_cuota(clave)

        cambios += 1
        logging.error(
            f"❌ {estado_error} en {servidor_fallido} ({fuente_anterior}) para {nombre} Ep {episodio_limpio}. "
            f"Cambio {cambios}/{MAX_CAMBIOS_FUENTE}..."
        )

        if cambios > MAX_CAMBIOS_FUENTE:
            logging.error("❌ Se alcanzó el máximo de cambios de fuente.")
            actualizar_sheet(
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
        temporal = (resultado == "cuota_agotada")

        # Se prefiere uno sin problemas de cuota...
        s_alterno = _siguiente_servidor_misma_fuente(
            driver_servidor, video, nombre, episodio_limpio,
            enlaces_fallidos, servidores_sin_cuota, download_dir
        )
        # ...pero si el archivo está caído / la descarga falló, un Mega sin cuota
        # (temporal) sigue siendo mejor que nada.
        if not s_alterno and not temporal:
            s_alterno = _siguiente_servidor_misma_fuente(
                driver_servidor, video, nombre, episodio_limpio,
                enlaces_fallidos, set(), download_dir
            )

        if s_alterno:
            video["link_descarga"] = s_alterno["enlace"]
            video["servidor_seleccionado"] = s_alterno["servidor"]

            actualizar_sheet(
                sheet_service=sheet_service,
                nombre_hoja="Animes",
                nombre_anime=nombre,
                episodio=episodio_limpio,
                nuevo_enlace=s_alterno["enlace"],
                nueva_fuente=fuente_anterior,
                fuentes_fallidas=", ".join(lista_excluidas),
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
        # Una cuota agotada es TEMPORAL: la fuente actual NO se marca como fallida
        temporal = (resultado == "cuota_agotada")

        lista_busqueda = _unir_fuentes(lista_excluidas, [fuente_anterior])
        if not temporal:
            lista_excluidas = lista_busqueda
            guardar_fuentes_fallidas(nombre, episodio_limpio, lista_excluidas)
        bitacora = [(fuente_anterior, f"falló: {estado_error}")]

        logging.info(
            f"🚫 Fuentes descartadas acumuladas: {', '.join(lista_busqueda)}")

        v_nuevo = buscar_fuente_alternativa(
            driver_servidor, nombre, episodio_limpio, lista_busqueda,
            download_dir,
            # cuota agotada: buscar algo que NO sea ese servidor; si no, solo se penaliza
            servidores_bloqueados=servidores_sin_cuota if temporal else None,
            servidores_penalizados=servidores_sin_cuota,
            bitacora=bitacora, persistir=not temporal
        )

        cadena_fallidas = ", ".join(lista_excluidas)

        if v_nuevo is None and temporal:
            # Sin alternativas: se queda Pendiente hasta que el servidor recupere la cuota
            logging.warning(
                f"⏳ {servidor_fallido} sin cuota y sin alternativas: se deja Pendiente.")
            actualizar_sheet(
                sheet_service=sheet_service,
                nombre_hoja="Animes",
                nombre_anime=nombre,
                episodio=episodio_limpio,
                fuentes_fallidas=cadena_fallidas or None,
                fecha_actualizacion=fecha_ahora,
                nuevo_estado="Pendiente"
            )
            enviar_mensaje_telegram(
                f"⏳ <b>Cuota agotada en {html.escape(servidor_fallido)}</b>\n\n"
                f"🎬 Anime: <b>{nombre_esc}</b>\n"
                f"📺 Episodio: <b>{episodio_esc}</b>\n"
                f"{resumen_fuentes_html(bitacora)}"
                f"🕒 Sin otro servidor disponible: queda Pendiente y se reintentará cuando haya cuota."
            )
            return False

        if v_nuevo is None:
            logging.error(
                "❌ No se encontraron fuentes alternativas válidas. Guardando 'Sin Fuentes'.")
            video["fuentes_fallidas"] = cadena_fallidas

            actualizar_sheet(
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
                f"📝 Fuentes fallidas: {html.escape(cadena_fallidas)}\n"
                f"{resumen_fuentes_html(bitacora)}"
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
        actualizar_sheet(
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
    servidores_sin_cuota = servidores_sin_cuota_vigentes()
    if servidores_sin_cuota:
        logging.info(f"⏳ Servidores sin cuota (vigente): {', '.join(sorted(servidores_sin_cuota))}")

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
import re
import os
import time
import logging
import os
from utilidades.archivos import extraer_episodio_archivo
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def normalizar_nombre(nombre):
    """
    Normaliza el nombre del anime para que sea comparable con los nombres de archivo.
    Elimina los espacios y caracteres no alfabéticos y convierte a minúsculas.

    Args:
        nombre (str): Nombre del anime a normalizar.

    Returns:
        str: Nombre normalizado del anime.
    """
    # Eliminar espacios, guiones, guiones bajos y convertir a minúsculas
    nombre_normalizado = re.sub(r'[^a-zA-Z0-9]', '', nombre.lower())
    return nombre_normalizado


def obtener_archivos_descargados(download_dir):
    """
    Obtiene una lista de los archivos descargados en el directorio de descargas.

    Args:
        download_dir (str): Directorio de descargas.

    Returns:
        list: Lista de nombres de archivos en el directorio de descargas.
    """
    try:
        archivos_descargados = os.listdir(download_dir)
        archivos_mp4 = [
            archivo for archivo in archivos_descargados if archivo.endswith(".mp4")]
        return archivos_mp4
    except FileNotFoundError:
        logging.error("El directorio de descargas no se encontró.")
        return []


def comparar_descargas(
    animes_a_descargar,
    archivos_descargados
):
    """
    Compara animes pendientes con los archivos descargados,
    teniendo en cuenta el episodio específico.

    Cada anime debe tener:

        {
            "nombre": "...",
            "episodio_buscado": 8,
            ...
        }

    Devuelve únicamente los animes cuyo episodio pendiente
    todavía no existe localmente.
    """

    animes_no_descargados = []

    # --------------------------------------------------
    # Crear una estructura con los archivos existentes
    # --------------------------------------------------

    archivos_info = []

    for archivo in archivos_descargados:

        nombre_archivo_normalizado = normalizar_nombre(
            archivo
        )

        episodio = extraer_episodio_archivo(
            archivo
        )

        archivos_info.append({
            "archivo": archivo,
            "nombre_normalizado": nombre_archivo_normalizado,
            "episodio": episodio
        })

    # --------------------------------------------------
    # Analizar cada anime pendiente
    # --------------------------------------------------

    for anime in animes_a_descargar:

        nombre_anime = anime["nombre"]

        episodio_buscado = anime.get(
            "episodio_buscado"
        )

        nombre_normalizado = normalizar_nombre(
            nombre_anime
        )

        encontrado = False

        for archivo in archivos_info:

            # El nombre del anime debe coincidir
            if nombre_normalizado not in archivo[
                "nombre_normalizado"
            ]:
                continue

            # El episodio debe coincidir
            if archivo["episodio"] == episodio_buscado:

                encontrado = True

                logging.info(
                    f"✅ Ya descargado: "
                    f"{nombre_anime} "
                    f"Episodio {episodio_buscado}"
                )

                break

        if not encontrado:

            logging.info(
                f"⬇️ Pendiente: "
                f"{nombre_anime} "
                f"Episodio {episodio_buscado}"
            )

            animes_no_descargados.append(
                anime
            )

    return animes_no_descargados


def tomar_captura_express(url, nombre_fuente, nombre_anime="", episodio=""):
    """
    Crea un driver temporal en modo headless, navega a la URL,
    guarda una captura de pantalla y cierra el navegador inmediatamente.
    """
    CARPETA_DEBUG = "debug_screenshots"
    os.makedirs(CARPETA_DEBUG, exist_ok=True)

    # Configuración del navegador temporal en modo headless (invisible)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        logging.info(f"📸 Generando captura express para {nombre_fuente}...")
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        
        time.sleep(3)

        # Formatear el nombre del archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fuente_limpia = re.sub(r'[^\w\-_\. ]', '_', str(nombre_fuente))
        anime_limpio = re.sub(r'[^\w\-_\. ]', '_', str(nombre_anime)) if nombre_anime else "busqueda"
        ep_texto = f"_EP{episodio}" if episodio else ""

        nombre_archivo = f"debug_{fuente_limpia}_{anime_limpio}{ep_texto}_{timestamp}.png"
        ruta_completa = os.path.join(CARPETA_DEBUG, nombre_archivo)

        driver.save_screenshot(ruta_completa)
        logging.info(f"✅ Captura express guardada en: {ruta_completa}")
        return ruta_completa

    except Exception as e:
        logging.error(f"⚠️ Error al tomar captura express en {nombre_fuente}: {e}")
        return None

    finally:
        # Garantiza el cierre del navegador incluso si ocurre un error
        if driver:
            driver.quit()

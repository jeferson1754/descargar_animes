# animes/buscador.py
import time
import re
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utilidades.navegador import configurar_navegador
from animes.comparador import tomar_captura_express
from notificaciones_telegram import enviar_mensaje_telegram

def extraer_nombres_anime(url, download_dir, max_reintentos=3):
    """
    Extrae únicamente los animes que tienen episodios pendientes 
    detectando la clase 'episode-badge episode-pending'.

    Implementa hasta 'max_reintentos' en caso de fallos de red o del navegador.
    """
    for intento in range(1, max_reintentos + 1):
        driver = None
        try:
            logging.info(
                f"🔄 Intentando extraer animes (Intento {intento}/{max_reintentos})...")
            driver = configurar_navegador(download_dir)

            if driver is None:
                logging.error(
                    f"❌ No se pudo iniciar el navegador en el intento {intento}.")
                if intento < max_reintentos:
                    time.sleep(3)
                continue

            driver.get(url)

            # 1. Esperar a que la tabla o el cuerpo cargue
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#animeTable tbody"))
                )
            except TimeoutException:
                logging.warning(
                    f"⚠️ No se encontró la tabla o la página demoró en cargar (Intento {intento}).")
                if intento < max_reintentos:
                    time.sleep(3)
                    continue
                return []

            tomar_captura_express(
                url=url,
                nombre_fuente="Servidor de Animes",
                nombre_anime="Todos",
                episodio="0"
            )

            # 2. BÚSQUEDA FILTRADA: Selecciona solo filas (tr) que tengan la etiqueta 'episode-pending'
            selector_pendientes = "#animeTable tbody tr:has(.episode-badge.episode-pending)"
            filas_pendientes = driver.find_elements(
                By.CSS_SELECTOR, selector_pendientes)

            # Respaldo: Si el navegador no soporta el pseudoselect :has(), usamos un filtro iterativo
            if not filas_pendientes:
                todas_las_filas = driver.find_elements(
                    By.CSS_SELECTOR, "#animeTable tbody tr")
                filas_pendientes = [
                    f for f in todas_las_filas
                    if len(f.find_elements(By.CSS_SELECTOR, ".episode-badge.episode-pending")) > 0
                ]

            animes = []

            for fila in filas_pendientes:
                try:
                    # ==========================================
                    # NOMBRE DEL ANIME
                    # ==========================================
                    elemento_nombre = fila.find_element(
                        By.CSS_SELECTOR, "td.fw-500")
                    nombre = driver.execute_script(
                        "return arguments[0].childNodes[0].textContent.trim();",
                        elemento_nombre
                    )

                    if not nombre:
                        continue

                    # ==========================================
                    # PROGRESO (Ejemplo: 7/12)
                    # ==========================================
                    progreso_elemento = fila.find_element(
                        By.CSS_SELECTOR, ".progress-cell span.small")
                    texto_progreso = progreso_elemento.text.strip()

                    match_progreso = re.search(
                        r"(\d+)\s*/\s*(\d+)", texto_progreso)
                    if not match_progreso:
                        continue

                    episodio_actual = int(match_progreso.group(1))
                    episodios_totales = int(match_progreso.group(2))

                    # ==========================================
                    # EPISODIOS PENDIENTES
                    # ==========================================
                    estado_elemento = fila.find_element(
                        By.CSS_SELECTOR, ".episode-badge.episode-pending")
                    match_pendientes = re.search(
                        r"(\d+)", estado_elemento.text.strip())

                    pendientes = int(match_pendientes.group(1)
                                     ) if match_pendientes else 1

                    # El episodio a buscar siempre es el siguiente al actual
                    episodio_buscado = episodio_actual + 1

                    anime = {
                        "nombre": nombre,
                        "episodio_actual": episodio_actual,
                        "episodios_totales": episodios_totales,
                        "pendientes": pendientes,
                        "episodio_buscado": episodio_buscado
                    }

                    animes.append(anime)

                except Exception as e:
                    logging.error(
                        f"⚠️ Error procesando fila con pendiente: {e}")

            # Éxito: retornamos los animes encontrados y salimos de la función
            return animes

        except Exception as e:
            logging.error(
                f"❌ Error inesperado durante la extracción (Intento {intento}): {e}")
            if intento < max_reintentos:
                time.sleep(3)

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # ============================================================
    # NOTIFICACIÓN POR TELEGRAM TRAS FALLAR TODOS LOS REINTENTOS
    # ============================================================
    logging.error(f"❌ Se agotaron los {max_reintentos} intentos para extraer los animes.")

    mensaje_error = (
        "⚠️ *Alerta de Automatización*\n\n"
        f"No se pudo extraer la lista de animes pendientes tras *{max_reintentos} intentos*.\n"
        "Captura de pantalla generada para análisis de depuración."
    )
    
    try:
        enviar_mensaje_telegram(mensaje_error)
    except Exception as e:
        logging.error(f"❌ Error al enviar notificación de fallo a Telegram: {e}")

    return []


def buscar_en_fuentes(animes, fuentes, excluir_fuente=None, download_dir=None):
    """
    Busca cada anime en las fuentes disponibles.
    Prueba las fuentes en orden hasta encontrar el episodio solicitado.
    Permite omitir fuentes mediante el parámetro 'excluir_fuente'.
    """
    # Normalizar fuentes a excluir en una lista en minúsculas
    if excluir_fuente is None:
        fuentes_excluidas = []
    elif isinstance(excluir_fuente, str):
        fuentes_excluidas = [excluir_fuente.strip().lower()]
    elif isinstance(excluir_fuente, list):
        fuentes_excluidas = [str(f).strip().lower() for f in excluir_fuente]
    else:
        fuentes_excluidas = []

    resultados = []

    for anime in animes:
        driver_capitulos = configurar_navegador(download_dir)

        nombre = anime.get("nombre")
        episodio_buscado = anime.get("episodio_buscado")

        logging.info("\n" + "=" * 60)
        logging.info(f"🔎 Buscando: {nombre}")
        logging.info(f"🎯 Episodio: {episodio_buscado}")
        logging.info("=" * 60)

        encontrado = False

        for fuente in fuentes:
            nombre_fuente = fuente["nombre"]

            # 1. Validar si la fuente está activa
            if not fuente.get("activa", True):
                continue

            # 2. Validar si la fuente debe ser excluida
            if nombre_fuente.strip().lower() in fuentes_excluidas:
                logging.info(f"⏭️ Omitiendo fuente excluida: {nombre_fuente}")
                continue

            url_fuente = fuente["url"]
            funcion_busqueda = fuente["buscar"]

            logging.info(f"🌐 Probando fuente: {nombre_fuente}")

            try:
                videos = funcion_busqueda(
                    driver_capitulos,
                    url_fuente,
                    [anime]
                )

                if videos:
                    logging.info(f"✅ Encontrado en {nombre_fuente}")

                    for video in videos:
                        video["fuente"] = nombre_fuente

                    resultados.extend(videos)
                    encontrado = True
                    break

                logging.error(f"❌ {nombre_fuente}: episodio no encontrado.")

            except Exception as e:
                logging.error(
                    f"⚠️ Error en {nombre_fuente}: {type(e).__name__}: {e}")

        driver_capitulos.quit()

        if not encontrado:
            logging.error(
                f"❌ No se encontró {nombre} episodio {episodio_buscado}")

    return resultados

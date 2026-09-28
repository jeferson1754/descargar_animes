
'''
import os
import sys

# Agrega la carpeta raíz del proyecto al path de Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DOWNLOAD_DIR
'''


from animes.comparador import tomar_captura_express
from utilidades.archivos import normalizar_nombre
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import difflib
import unicodedata
import logging
import re
from utilidades.navegador import configurar_navegador
from datetime import datetime
import json

URL_TIOANIME = "https://tioanime.com/"


def extraer_episodio_desde_url(url):
    match = re.search(r'-(\d+)$', url)

    if match:
        return int(match.group(1))

    return None


def buscar_pagina_principal(driver, url, anime, max_intentos=3):
    """Busca un episodio específico de un anime en la página principal.

    :param url: URL de la página principal (ej. TioAnime).
    :param anime: Diccionario con la información del anime a buscar: {
        "nombre": "...", "episodio_buscado": 8 }
    :param max_intentos: Número de reintentos en caso de fallo HTTP.
    :return: Lista con los datos del video si fue encontrado.
    """
    try:
        max_intentos = int(max_intentos)
    except (ValueError, TypeError):
        max_intentos = 3

    intentos = 0
    cargado_con_exito = False

    while intentos < max_intentos:
        try:
            print(f"🌐 Conectando a la URL mediante Selenium: {url}")
            driver.get(url)
            time.sleep(2)  # Pausa breve para permitir la carga del DOM

            tomar_captura_express(
                url=url,
                nombre_fuente="TioAnime",
                nombre_anime=anime["nombre"],
                episodio=anime["episodio_buscado"]
            )

            cargado_con_exito = True
            break
        except Exception as e:
            print(
                f"⚠️ Error al conectar con Selenium (Intento {intentos + 1}/{max_intentos}): {e}")
            intentos += 1
            if intentos < max_intentos:
                time.sleep(3)
            else:
                print("❌ Se agotaron los reintentos de conexión.")
                return []

    if not cargado_con_exito:
        return []


    # ============================================================
    # 2. PROCESAR HTML
    # ============================================================
    # ============================================================
    # 2. PROCESAR HTML CON SELENIUM
    # ============================================================
    try:
        # Extraer el HTML ya renderizado por Selenium/JavaScript
        soup = BeautifulSoup(driver.page_source, "html.parser")
        videos_encontrados = []

        nombre_anime = anime.get("nombre", "")
        episodio_buscado = str(anime.get("episodio_buscado", "")).strip()
        nombre_normalizado = normalizar_nombre(nombre_anime)
        url_actual = driver.current_url

        for enlace in soup.find_all("a", href=True):
            href = enlace["href"]
            url_completa = urljoin(url_actual, href)

            if "/ver/" not in url_completa:
                continue

            texto = enlace.get_text(" ", strip=True)
            texto_normalizado = normalizar_nombre(texto)

            # Validación de nombre: búsqueda por subcadena + difflib como respaldo
            coincide_nombre = (
                nombre_normalizado in texto_normalizado
                or bool(
                    difflib.get_close_matches(
                        nombre_normalizado,
                        [texto_normalizado],
                        n=1,
                        cutoff=0.6,
                    )
                )
            )

            if not coincide_nombre:
                continue

            # Obtener y validar episodio desde la URL
            episodio = extraer_episodio_desde_url(url_completa)

            if episodio is None:
                logging.warning(
                    f"⚠️ No se pudo determinar el episodio de: {url_completa}"
                )
                continue

            # Comparación segura convirtiendo ambos valores a string
            if str(episodio).strip() != episodio_buscado:
                logging.info(
                    f"⏭️ Episodio detectado: {episodio}. Se busca: {episodio_buscado}."
                )
                continue

            logging.info(
                f"✅ Episodio correcto encontrado: {episodio_buscado}"
            )

            nuevo_video = {
                "nombre": texto,
                "nombre_anime": nombre_anime,
                "enlace": url_completa,
                "episodio": episodio,
                "episodio_buscado": episodio_buscado,
            }

            if nuevo_video not in videos_encontrados:
                videos_encontrados.append(nuevo_video)

        return videos_encontrados

    except Exception as e:
        logging.error(f"❌ Error al procesar el contenido HTML: {e}")
        return []


def buscar_videos_tioanime(driver, url, animes):
    """
    Coordina la búsqueda en TioAnime.
    """
    logging.info(f"🔍 Buscando videos en: {url}")

    try:
        descargados = []


        for anime in animes:

            nombre_anime = anime["nombre"]
            episodio_buscado = anime.get("episodio_buscado")

            logging.info("\n" + "=" * 60)
            logging.info(f"📺 Anime: {nombre_anime}")
            logging.info(f"🎯 Episodio buscado: {episodio_buscado}")
            logging.info("=" * 60)

            # ---------------------------------------------
            # 1. Buscar en página principal
            # ---------------------------------------------

            # --------------------------------------------------
            # 1. Buscar en página principal
            # --------------------------------------------------
            resultado = buscar_pagina_principal(driver, URL_TIOANIME, anime)

            if resultado:
                item_principal = resultado[0]
                url_episodio = item_principal.get("enlace")
                episodio_confirmado = item_principal.get(
                    "episodio", episodio_buscado
                )
                logging.info(
                    f"✅ Encontrado en página principal: {url_episodio}")
            else:
                logging.info(
                    f"ℹ️ No encontrado en página principal: {nombre_anime}. Intentando búsqueda en perfil..."
                )

                # --------------------------------------------------
                # 2. Fallback: Búsqueda específica en el perfil
                # --------------------------------------------------
                url_anime = buscar_y_obtener_url_anime(driver, nombre_anime)

                if url_anime:
                    ultimo = obtener_ultimo_episodio(driver, url_anime)

                    if ultimo:
                        ultimo_ep = ultimo["episodio"]

                        if (
                            episodio_buscado is not None
                            and ultimo_ep < episodio_buscado
                        ):
                            logging.info(
                                f"⏳ El episodio {episodio_buscado} de {nombre_anime} aún no se estrena."
                            )
                            continue

                        if ultimo_ep == episodio_buscado:
                            url_episodio = ultimo["url"]
                        elif ultimo_ep > episodio_buscado:
                            especifico = buscar_episodio(
                                driver, url_anime, episodio_buscado
                            )
                            if especifico:
                                url_episodio = especifico["url"]

            # --------------------------------------------------
            # 3. Extraer y filtrar enlaces de descarga
            # --------------------------------------------------
            if url_episodio:
                links_descarga = buscar_boton_descarga(driver, url_episodio)

                # Validar que links_descarga sea siempre una lista
                if isinstance(links_descarga, str):
                    links_descarga = [{"servidor": "desconocido", "enlace": links_descarga}]
                elif not isinstance(links_descarga, list):
                    links_descarga = []

                # Precalcular lista de servidores aceptados en minúsculas
                servidores_aceptados_lower = [srv.lower() for srv in SERVIDORES_ACEPTADOS]

                # Filtrar asegurando que cada elemento sea un diccionario
                servidores_validos = [
                    s
                    for s in links_descarga
                    if isinstance(s, dict)
                    and s.get("servidor", "").lower() in servidores_aceptados_lower
                ]

                # Asignar servidor prioritario / disponible
                if servidores_validos:
                    enlace_principal = servidores_validos[0]["enlace"]
                elif links_descarga and isinstance(links_descarga[0], dict):
                    enlace_principal = links_descarga[0].get("enlace", url_episodio)
                else:
                    enlace_principal = url_episodio

                item_estructurado = {
                    "nombre": f"{nombre_anime} Episodio {episodio_confirmado}",
                    "nombre_anime": nombre_anime,
                    "enlace": url_episodio,
                    "episodio": episodio_confirmado,
                    "episodio_buscado": episodio_buscado,
                    "fuente": "TioAnime",
                    "link_descarga": enlace_principal,
                    "servidores": servidores_validos,
                }

                descargados.append(item_estructurado)

                logging.info(f"🚀 Agregado exitosamente | Link: {enlace_principal}")
            else:
                logging.error(
                    f"❌ No se pudo obtener la URL del episodio para {nombre_anime}."
                )

        with open("videos_tioanime.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(descargados, archivo_txt,
                        ensure_ascii=False, indent=4)
            
        return descargados

    finally:
        try:
            driver.quit()
            print("\n🔒 Driver principal cerrado correctamente.")
        except Exception as e:
            print(f"⚠️ Error al cerrar el driver: {e}")


def obtener_ultimo_episodio(driver, url_anime, max_intentos=3):
    if not url_anime:
        logging.error("❌ URL del anime vacía.")
        return None

    logging.info(f"📺 Consultando episodios: {url_anime}")

    pagina_cargada = False

    # --------------------------------------------------
    # Conexión y reintentos NATIVOS con Selenium
    # --------------------------------------------------
    for intento in range(1, max_intentos + 1):
        try:
            driver.get(url_anime)

            # Esperar a que la lista de episodios aparezca en el DOM
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ul.episodes-list li")
                )
            )
            pagina_cargada = True
            break  # Éxito, salir del bucle de reintentos

        except TimeoutException:
            logging.warning(
                f"⚠️ Tiempo de espera agotado al cargar la página "
                f"(intento {intento}/{max_intentos})"
            )
        except Exception as e:
            logging.warning(
                f"⚠️ Error navegando a la página "
                f"(intento {intento}/{max_intentos}): {e}"
            )

        if intento < max_intentos:
            logging.info("🔄 Reintentando...")

    if not pagina_cargada:
        logging.error("❌ No se pudo acceder a la página de episodios.")
        return None

    # --------------------------------------------------
    # Procesar HTML renderizado con BeautifulSoup
    # --------------------------------------------------
    try:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        episodios = []

        lista = soup.find("ul", class_="episodes-list")

        if not lista:
            logging.error("❌ No se encontró la lista de episodios.")
            return None

        elementos = lista.find_all("a")

        logging.info(f"🔎 Episodios encontrados: {len(elementos)}")

        for elemento in elementos:
            elemento_episodio = elemento.select_one("p span")

            if not elemento_episodio:
                continue

            texto_episodio = elemento_episodio.get_text(" ", strip=True)

            match = re.search(
                r"Episodio\s+(\d+)", texto_episodio, re.IGNORECASE
            )

            if not match:
                continue

            numero = int(match.group(1))

            href = elemento.get("href")

            if not href:
                continue

            enlace = urljoin(url_anime, href)

            episodios.append({"episodio": numero, "url": enlace})

            logging.info(f"🎬 Episodio {numero}: {enlace}")

        # --------------------------------------------------
        # Comprobar resultados y obtener el mayor
        # --------------------------------------------------
        if not episodios:
            logging.error("❌ No se encontraron episodios.")
            return None

        ultimo = max(episodios, key=lambda x: x["episodio"])

        logging.info(
            f"✅ Último episodio encontrado: {ultimo['episodio']}"
        )
        logging.info(f"🔗 URL: {ultimo['url']}")

        return ultimo

    except Exception as e:
        logging.error(f"❌ Error procesando episodios: {e}")
        return None

def buscar_boton_descarga(driver, video_url):
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



def buscar_y_obtener_url_anime(driver, nombre_anime):
    try:
        logging.info(f"🔍 Buscando en la web de TioAnime: {nombre_anime}")
        driver.get(URL_TIOANIME)

        wait = WebDriverWait(driver, 10)

        # 1. Esperar a que el input de búsqueda esté presente
        input_buscador = wait.until(
            EC.presence_of_element_located((By.ID, "search-anime"))
        )

        # 2. 🔑 CLAVE: Usar JavaScript para escribir el texto de golpe
        # (evita que el headless ignore o trunque las teclas tipeadas rápido)
        driver.execute_script(
            "arguments[0].value = arguments[1];", input_buscador, nombre_anime)

        # 3. Forzar el evento de cambio de input mediante JS para que el buscador despierte
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", input_buscador)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", input_buscador)

        # Dar un respiro para que carguen los resultados flotantes
        time.sleep(2)

        try:
            # 4. Intentar capturar el primer resultado del desplegable dinámico
            logging.info("⏳ Buscando en el menú desplegable...")
            primer_resultado = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div#search-results a.anime, div#search-results a"))
            )
            href_relativo = primer_resultado.get_attribute("href")

            if href_relativo and "javascript" not in href_relativo and "#" not in href_relativo:
                logging.info(
                    f"✅ ¡Encontrado en el desplegable! URL: {href_relativo}")
                return href_relativo
        except:
            logging.warning(
                "⚠️ El menú desplegable no respondió. Enviando tecla ENTER por seguridad...")

        # 5. Respaldo por ENTER si el desplegable falla
        input_buscador.send_keys(Keys.ENTER)
        time.sleep(3)

        primer_resultado_directorio = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "article.anime a, .anime-grid a"))
        )
        href_relativo = primer_resultado_directorio.get_attribute("href")

        logging.info(f"✅ ¡Encontrado por redirección! URL: {href_relativo}")
        return href_relativo

    except Exception as e:
        logging.error(
            f"❌ No se pudo encontrar el anime '{nombre_anime}' de ninguna forma: {e}")
        return None


def buscar_episodio(driver, url_anime, numero_episodio_buscado, max_intentos=3):
    """
    Busca un episodio específico de un anime en la página web usando Selenium.
    """

    if not url_anime:
        logging.error("❌ URL del anime vacía.")
        driver.quit()
        return None

    logging.info(
        f"📺 Consultando episodios para: {url_anime} (Buscando episodio {numero_episodio_buscado})")

    # --------------------------------------------------
    # Conexión y carga con Selenium (con reintentos)
    # --------------------------------------------------
    cargado_exitoso = False

    for intento in range(1, max_intentos + 1):
        try:
            driver.get(url_anime)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "ul.episodes-list li"))
            )
            cargado_exitoso = True
            break
        except Exception as e:
            logging.warning(
                f"⚠️ Error cargando la página (intento {intento}/{max_intentos}): {e}")
            if intento < max_intentos:
                logging.info("🔄 Reintentando...")
            else:
                logging.error(
                    "❌ No se pudo acceder a la página tras varios intentos.")
                driver.quit()
                return None

    if not cargado_exitoso:
        driver.quit()
        return None

    # --------------------------------------------------
    # Procesar HTML y buscar el episodio exacto
    # --------------------------------------------------
    try:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        driver.quit()  # Cerramos el driver ya que tenemos el HTML

        lista = soup.find("ul", class_="episodes-list")

        if not lista:
            logging.error(
                "❌ BeautifulSoup no encontró <ul class='episodes-list'>")
            return None

        elementos = lista.find_all("a")
        logging.info(
            f"🔎 Analizando {len(elementos)} elementos en la lista de episodios...")

        for elemento in elementos:
            elemento_episodio = elemento.select_one("p span")

            if not elemento_episodio:
                continue

            texto_episodio = elemento_episodio.get_text(" ", strip=True)

            match = re.search(
                r"Episodio\s+(\d+)",
                texto_episodio,
                re.IGNORECASE
            )

            if not match:
                continue

            numero = int(match.group(1))

            # Comparamos si el número coincide con el que estamos buscando
            if numero == int(numero_episodio_buscado):
                href = elemento.get("href")

                if not href:
                    continue

                enlace = urljoin(url_anime, href)

                logging.info(f"✅ ¡Episodio {numero} encontrado!")
                logging.info(f"🔗 URL: {enlace}")

                return {
                    "episodio": numero,
                    "url": enlace
                }

        logging.error(
            f"❌ No se encontró el episodio {numero_episodio_buscado}.")
        return None

    except Exception as e:
        logging.error(f"❌ Error procesando episodios: {e}")
        try:
            driver.quit()
        except:
            pass
        return None

# Servidores permitidos/prioritarios (en orden estricto de preferencia)
SERVIDORES_ACEPTADOS = ["mega", "mediafire", "voe", "mixdrop", "mp4upload", "gofile"]


def obtener_y_filtrar_servidores(
    driver, url_episodio, servidores_permitidos=None
):
  """Navega al episodio, obtiene todos los servidores, los filtra y los ordena por prioridad."""
  if servidores_permitidos is None:
    servidores_permitidos = SERVIDORES_ACEPTADOS

  # Normalizar la lista de permitidos a minúsculas
  permitidos_lower = [srv.lower() for srv in servidores_permitidos]

  # 1. Extraer todos los servidores presentes en la página del episodio
  todos_los_servidores = buscar_enlace_descarga_y_actualizar(
      driver, url_episodio
  )

  if not todos_los_servidores:
    logging.warning(
        f"⚠️ No se encontraron servidores en la URL: {url_episodio}"
    )
    return []

  servidores_filtrados = []

  # 2. Filtrar y asignar índice de prioridad
  for s in todos_los_servidores:
    nombre_servidor = str(s.get("servidor", "")).strip().lower()

    # Verificar si el servidor coincide con alguno de la lista permitida
    for prioridad, srv_permitido in enumerate(permitidos_lower):
      if srv_permitido in nombre_servidor:
        item = s.copy()
        item["_prioridad"] = prioridad
        servidores_filtrados.append(item)
        break

  # 3. Ordenar según la prioridad definida en SERVIDORES_ACEPTADOS
  servidores_filtrados.sort(key=lambda x: x["_prioridad"])

  # Eliminar el atributo temporal de prioridad
  for s in servidores_filtrados:
    s.pop("_prioridad", None)

  logging.info(
      f"🎯 Servidores encontrados: {len(todos_los_servidores)} | "
      f"Válidos y ordenados ({'/'.join(servidores_permitidos)}): {len(servidores_filtrados)}"
  )

  return servidores_filtrados

'''
if __name__ == "__main__":
    animes = [
        {
            "nombre": "Liar Game",
            "episodio_actual": 25,
            "episodios_totales": 26,
            "pendientes": 1,
            "episodio_buscado": 26
        }
    ]

    driver = configurar_navegador(DOWNLOAD_DIR, visor=True)
    SERVIDORES_ACEPTADOS = ["mega", "mediafire",
                            "voe", "mixdrop", "mp4upload", "gofile"]

    try:
        descargados = []

        for anime in animes:
            nombre_anime = anime["nombre"]
            episodio_buscado = anime["episodio_buscado"]

            print(
                f"\n============================================================"
            )
            print(
                f"🔎 Procesando: {nombre_anime} | Episodio: {episodio_buscado}"
            )
            print(
                f"============================================================"
            )

            url_episodio = None
            episodio_confirmado = episodio_buscado

            # --------------------------------------------------
            # 1. Buscar en página principal
            # --------------------------------------------------
            resultado = buscar_pagina_principal(driver, URL_TIOANIME, anime)

            if resultado:
                item_principal = resultado[0]
                url_episodio = item_principal.get("enlace")
                episodio_confirmado = item_principal.get(
                    "episodio", episodio_buscado
                )
                logging.info(
                    f"✅ Encontrado en página principal: {url_episodio}")
            else:
                logging.info(
                    f"ℹ️ No encontrado en página principal: {nombre_anime}. Intentando búsqueda en perfil..."
                )

                # --------------------------------------------------
                # 2. Fallback: Búsqueda específica en el perfil
                # --------------------------------------------------
                url_anime = buscar_y_obtener_url_anime(driver, nombre_anime)

                if url_anime:
                    ultimo = obtener_ultimo_episodio(driver, url_anime)

                    if ultimo:
                        ultimo_ep = ultimo["episodio"]

                        if (
                            episodio_buscado is not None
                            and ultimo_ep < episodio_buscado
                        ):
                            logging.info(
                                f"⏳ El episodio {episodio_buscado} de {nombre_anime} aún no se estrena."
                            )
                            continue

                        if ultimo_ep == episodio_buscado:
                            url_episodio = ultimo["url"]
                        elif ultimo_ep > episodio_buscado:
                            especifico = buscar_episodio(
                                driver, url_anime, episodio_buscado
                            )
                            if especifico:
                                url_episodio = especifico["url"]

            # --------------------------------------------------
            # 3. Extraer y filtrar enlaces de descarga
            # --------------------------------------------------
            if url_episodio:
                links_descarga = buscar_boton_descarga(driver, url_episodio)

                # Validar que links_descarga sea siempre una lista
                if isinstance(links_descarga, str):
                    links_descarga = [{"servidor": "desconocido", "enlace": links_descarga}]
                elif not isinstance(links_descarga, list):
                    links_descarga = []

                # Precalcular lista de servidores aceptados en minúsculas
                servidores_aceptados_lower = [srv.lower() for srv in SERVIDORES_ACEPTADOS]

                # Filtrar asegurando que cada elemento sea un diccionario
                servidores_validos = [
                    s
                    for s in links_descarga
                    if isinstance(s, dict)
                    and s.get("servidor", "").lower() in servidores_aceptados_lower
                ]

                # Asignar servidor prioritario / disponible
                if servidores_validos:
                    enlace_principal = servidores_validos[0]["enlace"]
                elif links_descarga and isinstance(links_descarga[0], dict):
                    enlace_principal = links_descarga[0].get("enlace", url_episodio)
                else:
                    enlace_principal = url_episodio

                item_estructurado = {
                    "nombre": f"{nombre_anime} Episodio {episodio_confirmado}",
                    "nombre_anime": nombre_anime,
                    "enlace": url_episodio,
                    "episodio": episodio_confirmado,
                    "episodio_buscado": episodio_buscado,
                    "fuente": "TioAnime",
                    "link_descarga": enlace_principal,
                    "servidores": servidores_validos,
                }

                descargados.append(item_estructurado)

                logging.info(f"🚀 Agregado exitosamente | Link: {enlace_principal}")
            else:
                logging.error(
                    f"❌ No se pudo obtener la URL del episodio para {nombre_anime}."
                )

        with open("videos_tioanime.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(descargados, archivo_txt,
                      ensure_ascii=False, indent=4)

    finally:
        try:
            driver.quit()
            print("\n🔒 Driver principal cerrado correctamente.")
        except Exception as e:
            print(f"⚠️ Error al cerrar el driver: {e}")
            '''
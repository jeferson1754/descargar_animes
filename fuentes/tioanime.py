import requests
import time
from bs4 import BeautifulSoup
import re
import logging
import unicodedata
from urllib.parse import urljoin
import difflib
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from utilidades.archivos import normalizar_nombre
from utilidades.navegador import configurar_navegador


URL_TIOANIME = "https://tioanime.com/anime/"

def extraer_episodio_desde_url(url):
    match = re.search(r'-(\d+)$', url)

    if match:
        return int(match.group(1))

    return None


def buscar_pagina_principal(url, anime, max_intentos=3):
    """
    Busca los animes en la página principal.

    `animes` debe ser una lista de diccionarios:
        {
            "nombre": "...",
            "episodio_buscado": 8,
            ...
        }
    """

    intentos = 0
    respuesta = None

    # ============================================================
    # 1. CONECTAR CON REINTENTOS
    # ============================================================

    while intentos < max_intentos:

        try:

            respuesta = requests.get(
                url,
                timeout=10
            )

            respuesta.raise_for_status()

            break

        except requests.exceptions.RequestException as e:

            intentos += 1

            logging.warning(
                f"⚠️ Error al conectar con la página "
                f"(Intento {intentos}/{max_intentos}): {e}"
            )

            if intentos < max_intentos:

                logging.info(
                    "🔄 Reintentando en 3 segundos..."
                )

                time.sleep(3)

            else:

                logging.error(
                    "❌ Se agotaron los reintentos."
                )

                return []

    # ============================================================
    # 2. PROCESAR HTML
    # ============================================================

    try:

        soup = BeautifulSoup(
            respuesta.text,
            "html.parser"
        )

        videos_encontrados = []

        # --------------------------------------------------------
        # Recorrer enlaces de la página
        # --------------------------------------------------------

        for enlace in soup.find_all(
            "a",
            href=True
        ):

            texto = enlace.get_text(
                " ",
                strip=True
            )

            href = enlace["href"]

            url_completa = urljoin(
                url,
                href
            )

            # ----------------------------------------------------
            # Aquí iría la condición específica de la fuente
            # ----------------------------------------------------

            if "/ver/" not in url_completa:
                continue

            # ----------------------------------------------------
            # Comparar contra cada anime pendiente
            # ----------------------------------------------------


            nombre_anime = anime["nombre"]

            nombre_normalizado = normalizar_nombre(
                nombre_anime
            )
            
            texto_normalizado = normalizar_nombre(
                texto
            )

            coincidencias = difflib.get_close_matches(
                nombre_normalizado,
                [texto_normalizado],
                n=1,
                cutoff=0.7
            )

            if not coincidencias:
                continue

            # ------------------------------------------------
            # Obtener episodio de la URL
            # ------------------------------------------------

            episodio = extraer_episodio_desde_url(
                url_completa
            )
            
            
            episodio_buscado = anime.get("episodio_buscado")

            if episodio is None:
                logging.warning(
                    f"⚠️ No se pudo determinar el episodio de: "
                    f"{url_completa}"
                )
                continue

            if episodio != episodio_buscado:
                logging.info(
                    f"⏭️ Episodio incorrecto: {episodio}. "
                    f"Se necesita el episodio {episodio_buscado}."
                )
                continue

            logging.info(
                f"✅ Episodio correcto encontrado: "
                f"{episodio_buscado}"
            )

            # ------------------------------------------------
            # Crear resultado conservando información
            # del anime original
            # ------------------------------------------------

            nuevo_video = {
                "nombre": texto,
                "nombre_anime": nombre_anime,
                "enlace": url_completa,
                "episodio": episodio,
                "episodio_buscado": episodio_buscado
            }

            # ------------------------------------------------
            # Evitar duplicados
            # ------------------------------------------------

            if nuevo_video not in videos_encontrados:

                videos_encontrados.append(
                    nuevo_video
                )

        return videos_encontrados

    except Exception as e:

        logging.error(
            f"❌ Error al procesar el contenido HTML: {e}"
        )

        return []


def buscar_videos_tioanime(driver, url, animes):

    """
    Coordina la búsqueda en TioAnime.
    """
    logging.info(f"🔍 Buscando videos en: {url}")

    resultados = []

    for anime in animes:

        nombre = anime["nombre"]
        episodio_buscado = anime.get("episodio_buscado")

        logging.info("\n" + "=" * 60)
        logging.info(f"📺 Anime: {nombre}")
        logging.info(f"🎯 Episodio buscado: {episodio_buscado}")
        logging.info("=" * 60)


        # ---------------------------------------------
        # 1. Buscar en página principal
        # ---------------------------------------------

        resultado = buscar_pagina_principal(
            url,
            anime
        )

        if resultado:

            resultados.extend(resultado)
            continue

        logging.info(
            "ℹ️ No encontrado en página principal."
        )
        
        # --------------------------------------------------
        # 2. Buscar página específica del anime
        # --------------------------------------------------
        
        url_anime = buscar_y_obtener_url_anime(driver,
                nombre
        )

        ultimo = obtener_ultimo_episodio(
            driver,
            url_anime
        )

        if not ultimo:

            logging.error(
                f"❌ No se pudieron obtener episodios "
                f"de {nombre}"
            )

            continue

        ultimo_episodio = ultimo["episodio"]

        logging.info(
            f"📊 Último disponible: "
            f"{ultimo_episodio} | "
            f"Buscado: {episodio_buscado}"
        )
        
        
        # --------------------------------------------------
        # 3. Comprobar si el episodio ya salió
        # --------------------------------------------------

        
        if (
            episodio_buscado is not None
            and ultimo_episodio < episodio_buscado
        ):

            logging.info(
                f"⏳ Todavía no salió el episodio "
                f"{episodio_buscado}."
            )

            continue
        
        # --------------------------------------------------
        # 4. Si el último es exactamente el buscado
        # --------------------------------------------------

        if ultimo_episodio == episodio_buscado:

            resultado_anime = {
                "nombre": (
                    f"{nombre} "
                    f"Episodio {episodio_buscado}"
                ),
                "nombre_anime": nombre,
                "enlace": ultimo["url"],
                "episodio": ultimo_episodio,
                "episodio_buscado": episodio_buscado
            }

            resultados.append(
                resultado_anime
            )

            logging.info(
                f"✅ Episodio {episodio_buscado} "
                f"encontrado."
            )

            continue
        
        # --------------------------------------------------
        # 5. El último episodio es mayor
        # --------------------------------------------------

        if ultimo_episodio > episodio_buscado:

            logging.info(
                f"ℹ️ El último episodio disponible "
                f"es {ultimo_episodio}, "
                f"pero se busca {episodio_buscado}. Buscando enlace específico..."
            )

            # Llamamos a la función para localizar exactamente el episodio solicitado
            episodio_especifico = buscar_episodio(driver, url_anime, episodio_buscado)

            if episodio_especifico:
                resultado_anime = {
                    "nombre": (
                        f"{nombre} "
                        f"Episodio {episodio_buscado}"
                    ),
                    "nombre_anime": nombre,
                    "enlace": episodio_especifico["url"],
                    "episodio": episodio_especifico["episodio"],
                    "episodio_buscado": episodio_buscado
                }

                resultados.append(
                    resultado_anime
                )

                logging.info(
                    f"✅ Episodio específico {episodio_buscado} "
                    f"encontrado y agregado."
                )
            else:
                logging.error(
                    f"❌ No se pudo encontrar el enlace "
                    f"para el episodio {episodio_buscado}."
                )

            continue


    return resultados



def obtener_ultimo_episodio(driver, url_anime, max_intentos=3):

    if not url_anime:
        logging.error("❌ URL del anime vacía.")
        return None
    
    logging.info(
        f"📺 Consultando episodios: {url_anime}"
    )
    
    respuesta = None

    # --------------------------------------------------
    # Conexión con reintentos
    # --------------------------------------------------

    for intento in range(1, max_intentos + 1):

        try:

            respuesta = requests.get(
                url_anime,
                timeout=15
            )

            respuesta.raise_for_status()
            
        except requests.exceptions.RequestException as e:

            logging.warning(
                f"⚠️ Error consultando episodios "
                f"(intento {intento}/{max_intentos}): {e}"
            )

            if intento < max_intentos:
                logging.info("🔄 Reintentando...")
            else:
                logging.error(
                    "❌ No se pudo acceder a la página."
                )
                return None

    # --------------------------------------------------
    # Procesar HTML
    # --------------------------------------------------

    try:
        
        driver.get(url_anime)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "ul.episodes-list li")
            )
        )

        html = driver.page_source

        soup = BeautifulSoup(
            html,
            "html.parser"
        )


        episodios = []

        # Los episodios están dentro de:
        # <a class="fa-play-circle ...">

        lista = soup.find(
            "ul",
            class_="episodes-list"
        )

        if not lista:
            logging.error(
                "❌ No se encontró la lista de episodios."
            )
            return None

        elementos = lista.find_all("a")

        logging.info(
            f"🔎 Episodios encontrados: "
            f"{len(elementos)}"
        )

        for elemento in elementos:

            elemento_episodio = elemento.select_one(
                "p span"
            )

            if not elemento_episodio:
                continue

            texto_episodio = elemento_episodio.get_text(
                " ",
                strip=True
            )

            match = re.search(
                r"Episodio\s+(\d+)",
                texto_episodio,
                re.IGNORECASE
            )

            if not match:
                continue

            numero = int(match.group(1))

            href = elemento.get("href")

            if not href:
                continue

            enlace = urljoin(
                url_anime,
                href
            )

            episodios.append({
                "episodio": numero,
                "url": enlace
            })

            logging.info(
                f"🎬 Episodio {numero}: {enlace}"
            )

        # --------------------------------------------------
        # Comprobar resultados
        # --------------------------------------------------

        if not episodios:

            logging.error(
                "❌ No se encontraron episodios."
            )

            return None

        # --------------------------------------------------
        # Obtener el mayor episodio
        # --------------------------------------------------

        ultimo = max(
            episodios,
            key=lambda x: x["episodio"]
        )

        logging.info(
            f"✅ Último episodio encontrado: "
            f"{ultimo['episodio']}"
        )

        logging.info(
            f"🔗 URL: {ultimo['url']}"
        )

        return ultimo

    except Exception as e:

        logging.error(
            f"❌ Error procesando episodios: {e}"
        )

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


def buscar_y_obtener_url_anime(driver, nombre_anime):
    try:
        logging.info(f"🔍 Buscando en la web de TioAnime: {nombre_anime}")
        driver.get("https://tioanime.com/")

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
                logging.info(f"✅ ¡Encontrado en el desplegable! URL: {href_relativo}")
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
    
    logging.info(f"📺 Consultando episodios para: {url_anime} (Buscando episodio {numero_episodio_buscado})")
    
    # --------------------------------------------------
    # Conexión y carga con Selenium (con reintentos)
    # --------------------------------------------------
    cargado_exitoso = False
    
    for intento in range(1, max_intentos + 1):
        try:
            driver.get(url_anime)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.episodes-list li"))
            )
            cargado_exitoso = True
            break
        except Exception as e:
            logging.warning(f"⚠️ Error cargando la página (intento {intento}/{max_intentos}): {e}")
            if intento < max_intentos:
                logging.info("🔄 Reintentando...")
            else:
                logging.error("❌ No se pudo acceder a la página tras varios intentos.")
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
            logging.error("❌ BeautifulSoup no encontró <ul class='episodes-list'>")
            return None

        elementos = lista.find_all("a")
        logging.info(f"🔎 Analizando {len(elementos)} elementos en la lista de episodios...")

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

        logging.error(f"❌ No se encontró el episodio {numero_episodio_buscado}.")
        return None

    except Exception as e:
        logging.error(f"❌ Error procesando episodios: {e}")
        try:
            driver.quit()
        except:
            pass
        return None

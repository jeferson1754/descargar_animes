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




# pruebas_tioanime.py


URL_TIOANIME = "https://monoschinos.st/"


def extraer_episodio_desde_url(url):
    """
    Extrae el número de episodio de la URL considerando barras diagonales al final.
    """
    try:
        url_limpia = url.rstrip('/')
        match = re.search(r'-(\d+)$', url_limpia)
        if match:
            return int(match.group(1))
    except Exception as e:
        print(f"⚠️ Error en extraer_episodio_desde_url para '{url}': {e}")
    return None


def buscar_pagina_principal(driver, url, animes, max_intentos=3):
    """
    Busca los animes analizando la página principal con BeautifulSoup (requests),
    validando las URLs por su estructura de episodio.
    """

    """
    Busca los animes analizando la página principal directamente con Selenium (driver),
    validando las URLs por su estructura de episodio.
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
                nombre_fuente="MonosChinos",
                nombre_anime=animes["nombre"],
                episodio=animes["episodio_buscado"]
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

    # Obtener tarjetas directamente usando Selenium
# 1. Obtener las tarjetas usando el selector de la nueva estructura
    try:
        # Busca los artículos dentro del contenedor grid del nuevo diseño
        tarjetas = driver.find_elements(By.CSS_SELECTOR, "div.grid article")
        if not tarjetas:
            # Fallback en caso de que cambie la clase del contenedor principal
            tarjetas = driver.find_elements(By.CSS_SELECTOR, "article")

        print(f"🔍 Total de tarjetas 'article' encontradas: {len(tarjetas)}")
    except Exception as e:
        print(f"❌ Error al buscar tarjetas en el DOM: {e}")
        return []

    if not tarjetas:
        print("⚠️ Advertencia: No se encontraron elementos 'article'.")
        return []
    videos_encontrados = []

    for index, tarjeta in enumerate(tarjetas):
        try:
            # 1. Extraer enlace <a> (prioriza a.card-wrap y cae en a[href])
            try:
                enlace_tag = tarjeta.find_element(By.CSS_SELECTOR, "a.card-wrap, a[href]")
                href = enlace_tag.get_attribute("href")
            except Exception:
                continue

            if not href:
                continue

            url_completa = urljoin(url, href)

            # 2. Extraer Título/Nombre del anime
            texto = ""
            try:
                # Primero busca el h3 del nuevo diseño
                texto = tarjeta.find_element(By.CSS_SELECTOR, "h3.card-title, h3").text.strip()
            except Exception:
                try:
                    # Fallback: etiqueta span original
                    texto = tarjeta.find_element(By.CSS_SELECTOR, "span").text.strip()
                except Exception:
                    # Fallback: atributo 'title'
                    title_attr = enlace_tag.get_attribute("title")
                    if title_attr:
                        texto = title_attr.replace("Ver ", "").split("episodio")[0].strip()

            # Fallback de emergencia desde la URL si sigue vacío
            if not texto:
                partes_url = [p for p in url_completa.split("/") if p]
                if partes_url:
                    texto = partes_url[-1].replace("-", " ").title()

            # 3. Extraer Episodio
            episodio = None
            try:
                # Busca en div.font-mono ("EP 13") o cae en la etiqueta <u> previa
                ep_tag = tarjeta.find_element(By.CSS_SELECTOR, "div.font-mono, u")
                match_ep = re.search(r'\d+', ep_tag.text)
                if match_ep:
                    episodio = int(match_ep.group())
            except Exception:
                # Fallback extra: intentar extraer el número de episodio al final de la URL
                match_ep = re.search(r'episodio-(\d+)|-(\d+)$', url_completa)
                if match_ep:
                    episodio = int(next(g for g in match_ep.groups() if g is not None))

            # Si no se pudo obtener del <u>, usar fallback de la URL
            if episodio is None:
                episodio = extraer_episodio_desde_url(url_completa)

            if episodio is None:
                continue

            # 4. Validar coincidencias con el anime buscado
            nombre_anime = animes.get("nombre", "") if isinstance(
                animes, dict) else str(animes)
            episodio_buscado = animes.get(
                "episodio_buscado") if isinstance(animes, dict) else None

            nombre_normalizado = normalizar_nombre(nombre_anime)
            texto_normalizado = normalizar_nombre(texto)

            coincidencias = difflib.get_close_matches(
                nombre_normalizado,
                [texto_normalizado],
                n=1,
                cutoff=0.7
            )

            if not coincidencias:
                continue

            if episodio_buscado is not None and episodio != episodio_buscado:
                print(
                    f"⏭️ Coincidencia de nombre ('{texto}'), pero el episodio no coincide. Hallado: {episodio} | Buscado: {episodio_buscado}")
                continue

            print(
                f"🎯 ¡MATCH EXITOSO! '{texto}' | Enlace: {url_completa} | Ep. {episodio}")

            nuevo_video = {
                "nombre": texto,
                "nombre_anime": nombre_anime,
                "enlace": url_completa,
                "episodio": episodio,
                "episodio_buscado": episodio_buscado
            }

            if nuevo_video not in videos_encontrados:
                videos_encontrados.append(nuevo_video)

        except Exception as inner_e:
            print(f"❌ Error procesando la tarjeta [{index}]: {inner_e}")
            continue

    return videos_encontrados


def buscar_boton_descarga(driver, video_url):
    try:
        driver.get(video_url)
        wait = WebDriverWait(driver, 10)

        # Esperar a que los enlaces directos de descarga estén presentes en el DOM
        elementos_enlace = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.direct-link"))
        )

        links_descarga = []
        for elem in elementos_enlace:
            try:
                servidor = elem.text.strip()
                url_descarga = elem.get_attribute("href")

                if url_descarga:
                    links_descarga.append({
                        "servidor": servidor,
                        "formato": "N/A",
                        "calidad": "N/A",
                        "audio": "N/A",
                        "enlace": url_descarga
                    })
            except Exception:
                continue

        if links_descarga:
            print(f"✅ Se extrajeron {len(links_descarga)} enlaces de descarga de {video_url}")
            return links_descarga
        else:
            print(f"⚠️ No se encontraron enlaces de descarga para {video_url}")
            return None

    except Exception as e:
        print(f"❌ Error al extraer enlaces de descarga en {video_url}: {e}")
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
        logging.info(f"🔍 Buscando en la web: {nombre_anime}")
        driver.get(URL_TIOANIME)  # Ajusta la variable de la URL según corresponda

        wait = WebDriverWait(driver, 10)

        # 1. Esperar al input mediante name="q"
        input_buscador = wait.until(
            EC.presence_of_element_located((By.NAME, "q"))
        )

        # 2. Escribir el nombre del anime mediante JavaScript para evitar caracteres truncados
        input_buscador.clear()
        driver.execute_script(
            "arguments[0].value = arguments[1];", input_buscador, nombre_anime
        )

        # 3. Notificar a la página del cambio de input
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            input_buscador,
        )
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
            input_buscador,
        )

        time.sleep(1)

        # 4. Enviar el formulario de búsqueda
        input_buscador.send_keys(Keys.ENTER)
        logging.info(
            "⏳ Formulario enviado. Esperando resultados de búsqueda..."
        )

        # 5. Capturar el primer resultado usando la estructura 'article a.card-wrap'
        primer_resultado = wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "article a.card-wrap"
                )
            )
        )
        href_enlace = primer_resultado.get_attribute("href")

        print(f"✅ ¡Encontrado! URL: {href_enlace}")
        return href_enlace

    except Exception as e:
        logging.error(f"❌ No se pudo encontrar el anime '{nombre_anime}': {e}")
        return None

def obtener_ultimo_episodio(driver, url_anime, max_intentos=3):
    if not url_anime:
        logging.error("❌ URL del anime vacía.")
        return None

    print(f"📺 Consultando episodios: {url_anime}")

    # --------------------------------------------------
    # Navegación con reintentos mediante Selenium
    # --------------------------------------------------
    cargado = False
    for intento in range(1, max_intentos + 1):
        try:
            driver.get(url_anime)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.eplist li"))
            )
            cargado = True
            break
        except Exception as e:
            print(
                f"⚠️ Error al cargar la página (intento {intento}/{max_intentos}): {e}"
            )
            if intento < max_intentos:
                logging.info("🔄 Reintentando...")
                time.sleep(2)
            else:
                logging.error("❌ No se pudo acceder a la página con Selenium.")
                return None

    if not cargado:
        return None

    # --------------------------------------------------
    # Extracción de episodios con Selenium
    # --------------------------------------------------
    try:
        # Localizar los enlaces dentro de <ul class="eplist">
        elementos_a = driver.find_elements(By.CSS_SELECTOR, "ul.eplist a.ep-card")
        print(f"🔎 Episodios encontrados: {len(elementos_a)}")

        episodios = []

        for elemento in elementos_a:
            try:
                # Extraer la URL
                enlace = elemento.get_attribute("href")
                if not enlace:
                    continue

                # Extraer la etiqueta <h3 class="ep-title">
                etiqueta_ep = elemento.find_element(By.CSS_SELECTOR, "h3.ep-title")
                texto_episodio = etiqueta_ep.text.strip()

                # Buscar "Capítulo X" o "Episodio X"
                match = re.search(
                    r"(?:Capítulo|Episodio)\s+(\d+)", texto_episodio, re.IGNORECASE
                )
                
                # Respaldo: si falla el texto, intentar extraer el número directamente de la URL
                if not match:
                    match = re.search(r"episodio-(\d+)", enlace, re.IGNORECASE)

                if not match:
                    continue

                numero = int(match.group(1))

                episodios.append({"episodio": numero, "url": enlace})
                print(f"🎬 Episodio {numero}: {enlace}")

            except Exception:
                # Omitir elementos si difieren de la estructura requerida
                continue

        # --------------------------------------------------
        # Obtener el episodio más reciente (mayor número)
        # --------------------------------------------------
        if not episodios:
            print("❌ No se encontraron episodios válidos.")
            return None

        ultimo = max(episodios, key=lambda x: x["episodio"])

        print(f"✅ Último episodio encontrado: {ultimo['episodio']}")
        print(f"🔗 URL: {ultimo['url']}")

        return ultimo

    except Exception as e:
        print(f"❌ Error procesando episodios con Selenium: {e}")
        return None

def buscar_episodio(driver, url_anime, numero_episodio_buscado, max_intentos=3):
    """Busca un episodio específico de un anime en la página web usando exclusivamente Selenium."""

    if not url_anime:
        logging.error("❌ URL del anime vacía.")
        return None

    logging.info(
        f"📺 Consultando episodios para: {url_anime} (Buscando episodio {numero_episodio_buscado})"
    )

    # --------------------------------------------------
    # Conexión y carga con Selenium (con reintentos)
    # --------------------------------------------------
    cargado_exitoso = False

    for intento in range(1, max_intentos + 1):
        try:
            driver.get(url_anime)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.eplist li"))
            )
            cargado_exitoso = True
            break
        except Exception as e:
            logging.warning(
                f"⚠️ Error cargando la página (intento {intento}/{max_intentos}): {e}"
            )
            if intento < max_intentos:
                logging.info("🔄 Reintentando...")
                time.sleep(2)
            else:
                logging.error(
                    "❌ No se pudo acceder a la página tras varios intentos."
                )
                return None

    if not cargado_exitoso:
        return None

    # --------------------------------------------------
    # Buscar el episodio exacto mediante Selenium
    # --------------------------------------------------
    try:
        elementos_a = driver.find_elements(By.CSS_SELECTOR, "ul.eplist a.ep-card")
        logging.info(
            f"🔎 Analizando {len(elementos_a)} elementos en la lista de episodios..."
        )

        for elemento in elementos_a:
            try:
                enlace = elemento.get_attribute("href")
                if not enlace:
                    continue

                # Intentar extraer el número desde el título HTML <h3 class="ep-title">
                match = None
                try:
                    etiqueta_ep = elemento.find_element(By.CSS_SELECTOR, "h3.ep-title")
                    texto_episodio = etiqueta_ep.text.strip()
                    match = re.search(
                        r"(?:Capítulo|Episodio)\s+(\d+)", texto_episodio, re.IGNORECASE
                    )
                except Exception:
                    pass

                # Respaldo: si falla la etiqueta o el texto, buscar en la URL
                if not match:
                    match = re.search(r"episodio-(\d+)", enlace, re.IGNORECASE)

                if not match:
                    continue

                numero = int(match.group(1))

                # Si coincide el número buscado, retornamos la información
                if numero == int(numero_episodio_buscado):
                    logging.info(f"✅ ¡Episodio {numero} encontrado!")
                    logging.info(f"🔗 URL: {enlace}")

                    return {"episodio": numero, "url": enlace}

            except Exception:
                # Si un elemento falla, pasa al siguiente
                continue

        logging.error(
            f"❌ No se encontró el episodio {numero_episodio_buscado}."
        )
        return None

    except Exception as e:
        logging.error(f"❌ Error procesando episodios con Selenium: {e}")
        return None
import logging

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


def buscar_videos_monoschinos(driver, url, animes):
    """Coordina la búsqueda en AnimeFLV e integra la extracción y filtrado de servidores de descarga."""
    logging.info(f"🔍 Buscando videos en: {url}")
    resultados = []

    for anime in animes:
        nombre = anime["nombre"]
        episodio_buscado = anime.get("episodio_buscado")

        logging.info("\n" + "=" * 60)
        logging.info(f"📺 Anime: {nombre}")
        logging.info(f"🎯 Episodio buscado: {episodio_buscado}")
        logging.info("=" * 60)

        url_episodio = None
        episodio_confirmado = episodio_buscado

        # ---------------------------------------------
        # 1. Buscar en página principal
        # ---------------------------------------------
        resultado_principal = buscar_pagina_principal(driver, url, anime)

        if resultado_principal:
            # Si se encontró en la principal, extraemos la URL del primer resultado
            url_episodio = resultado_principal[0].get("enlace")
            logging.info(
                f"✅ Encontrado en página principal: {url_episodio}"
            )

        # --------------------------------------------------
        # 2. Buscar página específica del anime (si no estaba en la principal)
        # --------------------------------------------------
        if not url_episodio:
            logging.info(
                "ℹ️ No encontrado en página principal. Buscando en perfil del anime..."
            )
            url_anime = buscar_y_obtener_url_anime(driver, nombre)

            ultimo = obtener_ultimo_episodio(driver, url_anime)

            if not ultimo:
                logging.error(
                    f"❌ No se pudieron obtener episodios de {nombre}"
                )
                continue

            ultimo_episodio = ultimo["episodio"]
            logging.info(
                f"📊 Último disponible: {ultimo_episodio} | Buscado: {episodio_buscado}"
            )

            # Comprobar si aún no se ha estrenado
            if (
                episodio_buscado is not None
                and ultimo_episodio < episodio_buscado
            ):
                logging.info(
                    f"⏳ Todavía no salió el episodio {episodio_buscado}."
                )
                continue

            # Si el último es exactamente el buscado
            if ultimo_episodio == episodio_buscado:
                url_episodio = ultimo["url"]
                logging.info(f"✅ Episodio {episodio_buscado} localizado.")

            # Si el último es mayor, buscamos el episodio exacto
            elif ultimo_episodio > episodio_buscado:
                logging.info(
                    f"ℹ️ El último es {ultimo_episodio}. Buscando episodio {episodio_buscado}..."
                )
                especifico = buscar_episodio(
                    driver, url_anime, episodio_buscado
                )

                if especifico:
                    url_episodio = especifico["url"]
                    logging.info(
                        f"✅ Episodio específico {episodio_buscado} localizado."
                    )
                else:
                    logging.error(
                        f"❌ No se pudo encontrar el enlace para el episodio {episodio_buscado}."
                    )
                    continue

        # --------------------------------------------------
        # 3. EXTRAER Y FILTRAR SERVIDORES DE DESCARGA
        # --------------------------------------------------
        if url_episodio:
            links_descarga = buscar_boton_descarga(driver, url_episodio)

            # Filtrar enlaces según los servidores aceptados
            servidores_validos = [
                s
                for s in links_descarga
                if s.get("servidor", "").lower()
                in [srv.lower() for srv in SERVIDORES_ACEPTADOS]
            ]

            # Asignar servidor prioritario (o primer disponible si no coincide el filtro)
            if servidores_validos:
                enlace_principal = servidores_validos[0]["enlace"]
            elif links_descarga:
                enlace_principal = links_descarga[0]["enlace"]
            else:
                enlace_principal = url_episodio

            resultado_anime = {
                "nombre": f"{nombre} Episodio {episodio_confirmado}",
                "nombre_anime": nombre,
                "enlace": url_episodio,
                "episodio": episodio_confirmado,
                "episodio_buscado": episodio_buscado,
                "fuente": "AnimeFLV",
                "link_descarga": enlace_principal,
                "servidores": servidores_validos,
            }

            resultados.append(resultado_anime)
            logging.info(
                f"🚀 Agregado exitosamente con {len(servidores_validos)} servidor(es) filtrado(s)."
            )

    return resultados

'''
if __name__ == "__main__":
    animes = [
        {
            "nombre": "Reiwa no Dara-san",
            "episodio_actual": 11,
            "episodios_totales": 13,
            "pendientes": 1,
            "episodio_buscado": 12
        },
        {
            "nombre": "Super no Ura de Yani Suu Futari",
            "episodio_actual": 11,
            "episodios_totales": 12,
            "pendientes": 1,
            "episodio_buscado": 12
        }
    ]

    driver = configurar_navegador(DOWNLOAD_DIR, visor=True)
    SERVIDORES_ACEPTADOS = ["mega", "mediafire", "voe", "mixdrop", "mp4upload", "gofile"]

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
                logging.info(f"✅ Encontrado en página principal: {url_episodio}")
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

                # Filtrar enlaces según los servidores aceptados
                servidores_validos = [
                    s
                    for s in links_descarga
                    if s.get("servidor", "").lower()
                    in [srv.lower() for srv in SERVIDORES_ACEPTADOS]
                ]

                # Asignar servidor prioritario (o primer disponible si no coincide el filtro)
                if servidores_validos:
                    enlace_principal = servidores_validos[0]["enlace"]
                elif links_descarga:
                    enlace_principal = links_descarga[0]["enlace"]
                else:
                    enlace_principal = url_episodio

                item_estructurado = {
                    "nombre": f"{nombre_anime} Episodio {episodio_confirmado}",
                    "nombre_anime": nombre_anime,
                    "enlace": url_episodio,
                    "episodio": episodio_confirmado,
                    "episodio_buscado": episodio_buscado,
                    "fuente": "Monoschinos",
                    "link_descarga": enlace_principal,
                    "servidores": servidores_validos,
                }

                descargados.append(item_estructurado)
                
                
                logging.info(
                    f"🚀 Agregado exitosamente | Link: {enlace_principal}"
                )
            else:
                logging.error(
                    f"❌ No se pudo obtener la URL del episodio para {nombre_anime}."
                )

        with open("videos_monoschinos.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(descargados, archivo_txt,
                  ensure_ascii=False, indent=4)

    finally:
        try:
            driver.quit()
            print("\n🔒 Driver principal cerrado correctamente.")
        except Exception as e:
            print(f"⚠️ Error al cerrar el driver: {e}")

    
    # Procesamiento en la nube
    if descargados:
        videos_finales = proceso_nube_buscar_y_guardar_sheets(
            DOWNLOAD_DIR, descargados
        )
    else:
        logging.error("❌ No hay elementos para procesar en la nube.")
    '''
    
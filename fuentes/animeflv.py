import os
import sys

# Sube un nivel desde la carpeta /fuentes a la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
from config import DOWNLOAD_DIR
import os
import sys

from datetime import datetime
import json

# Sube un nivel desde la carpeta /fuentes a la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ahora puedes importar config sin errores


# pruebas_tioanime.py


URL_TIOANIME = "https://www.animeflv.one"


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
                nombre_fuente="AnimeFLV",
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
        tarjetas = driver.find_elements(By.CSS_SELECTOR, "div.ul.hm article.li")
        if not tarjetas:
            # Fallback en caso de que varíe el contenedor principal
            tarjetas = driver.find_elements(By.CSS_SELECTOR, "article.li")

        print(f"🔍 Total de tarjetas 'article.li' encontradas: {len(tarjetas)}")
    except Exception as e:
        print(f"❌ Error al buscar tarjetas en el DOM: {e}")
        return []

    if not tarjetas:
        print("⚠️ Advertencia: No se encontraron elementos 'article.li'.")
        return []

    videos_encontrados = []

    for index, tarjeta in enumerate(tarjetas):
        try:
            # Extraer enlace <a>
            try:
                enlace_tag = tarjeta.find_element(By.CSS_SELECTOR, "a[href]")
                href = enlace_tag.get_attribute("href")
            except Exception:
                continue

            if not href:
                continue

            url_completa = urljoin(url, href)

            # 2. Extraer Título/Nombre del anime (de la etiqueta <span>)
            texto = ""
            try:
                span_tag = tarjeta.find_element(By.CSS_SELECTOR, "span")
                texto = span_tag.text.strip()
            except Exception:
                # Fallback: intentar desde el atributo 'title' del enlace
                title_attr = enlace_tag.get_attribute("title")
                if title_attr:
                    texto = title_attr.replace("Ver ", "").split("episodio")[0].strip()

            if not texto:
                partes_url = [p for p in url_completa.split("/") if p]
                if partes_url:
                    texto = partes_url[-1].replace("-", " ").title()

            # 3. Extraer Episodio (de la etiqueta <u> o de la URL)
            episodio = None
            try:
                u_tag = tarjeta.find_element(By.CSS_SELECTOR, "u")
                if u_tag:
                    match_ep = re.search(r'\d+', u_tag.text)
                    if match_ep:
                        episodio = int(match_ep.group())
            except Exception:
                pass

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
        ventana_principal = driver.current_window_handle
        driver.get(video_url)
        wait = WebDriverWait(driver, 10)

        # 1. Bucle para asegurar el clic hasta que la lista de servidores sea visible
        tabla_visible = False
        intentos = 0
        max_intentos = 5

        while not tabla_visible and intentos < max_intentos:
            intentos += 1
            try:
                # Selector del nuevo botón: div con clase 'dwn' o 'dwn se'
                boton_dwld = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "div.dwn.se, div.dwn")
                    )
                )
                driver.execute_script("arguments[0].click();", boton_dwld)
                time.sleep(1.5)  # Pausa para animación y posibles popups

                # 🛡️ Cerrar pestañas/ventanas de anuncios emergentes
                if len(driver.window_handles) > 1:
                    for handle in driver.window_handles:
                        if handle != ventana_principal:
                            driver.switch_to.window(handle)
                            driver.close()
                    driver.switch_to.window(ventana_principal)

                # Verificar si la lista 'ul.uldwn' ya es visible y contiene filas
                lista_elementos = driver.find_element(By.CSS_SELECTOR, "ul.uldwn")
                if lista_elementos.is_displayed():
                    # Buscar filas excluyendo la cabecera (li.t)
                    filas = lista_elementos.find_elements(By.CSS_SELECTOR, "li:not(.t)")
                    if len(filas) >= 1:
                        tabla_visible = True
            except Exception:
                time.sleep(1)

        if not tabla_visible:
            print(
                f"❌ No se pudo desplegar la lista de servidores tras {max_intentos} intentos en {video_url}"
            )
            return None

        # 2. Extraer información de la lista 'ul.uldwn'
        lista_servidores = driver.find_element(By.CSS_SELECTOR, "ul.uldwn")
        filas = lista_servidores.find_elements(By.CSS_SELECTOR, "li:not(.t)")

        links_descarga = []
        for fila in filas:
            columnas = fila.find_elements(By.XPATH, "./div")
            if len(columnas) >= 5:
                servidor = columnas[0].text.strip()
                formato = columnas[1].text.strip()
                calidad = columnas[2].text.strip()
                audio = columnas[3].text.strip()

                try:
                    link_tag = columnas[4].find_element(By.TAG_NAME, "a")
                    url_descarga = link_tag.get_attribute("href")

                    links_descarga.append({
                        "servidor": servidor,
                        "formato": formato,
                        "calidad": calidad,
                        "audio": audio,
                        "enlace": url_descarga
                    })
                except Exception:
                    continue

        if links_descarga:
            print(
                f"✅ Se extrajeron {len(links_descarga)} enlaces de descarga de {video_url}"
            )
            return links_descarga
        else:
            print(f"⚠️ La lista de servidores está vacía para {video_url}")
            return None

    except Exception as e:
        try:
            if len(driver.window_handles) > 1:
                for handle in driver.window_handles:
                    if handle != driver.current_window_handle:
                        driver.switch_to.window(handle)
                        driver.close()
                driver.switch_to.window(driver.current_window_handle)
        except Exception:
            pass

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
        driver.get(URL_TIOANIME)

        wait = WebDriverWait(driver, 10)

        # 1. Esperar al input mediante name="buscar"
        input_buscador = wait.until(
            EC.presence_of_element_located((By.NAME, "buscar"))
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

        # 5. Capturar el primer resultado del listado devuelto
        primer_resultado = wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "article.anime a, .anime-grid a, ul.Animes a, div.Animes a",
                )
            )
        )
        href_relativo = primer_resultado.get_attribute("href")

        logging.info(f"✅ ¡Encontrado! URL: {href_relativo}")
        return href_relativo

    except Exception as e:
        logging.error(f"❌ No se pudo encontrar el anime '{nombre_anime}': {e}")
        return None


def buscar_videos_animeflv(driver, url, animes):
    """
    Coordina la búsqueda en Jkanime.
    """
    logging.info(f"🔍 Buscando videos en: {url}")

    resultados = []

    for anime in animes:

        nombre_anime = anime['nombre']
        episodio_buscado = anime['episodio_buscado']

        logging.info("\n" + "=" * 60)
        logging.info(f"📺 Anime: {nombre_anime}")
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
            for item in resultado:
                url_episodio = item.get('enlace')
                links_descarga = buscar_boton_descarga(
                    driver, url_episodio) if url_episodio else []

                # Guardar todos los enlaces de descarga disponibles sin filtrar
                enlace_principal = links_descarga if links_descarga else []

                # Si falla todo, usar la URL genérica del episodio
                if not enlace_principal:
                    enlace_principal = url_episodio

                # Estructura limpia compatible con tu función de nube
                item_estructurado = {
                    "nombre": item.get('nombre', nombre_anime),
                    "nombre_anime": nombre_anime,
                    "enlace": url_episodio,
                    "episodio": item.get('episodio', episodio_buscado),
                    "episodio_buscado": episodio_buscado,
                    "fuente": "AnimeFLV",
                    # <--- Aquí va el enlace seleccionado automáticamente
                    "link_descarga": enlace_principal,
                }

                resultados.append(item_estructurado)
            else:
                logging.info(
                    f"ℹ️ No encontrado en página principal: {nombre_anime}")
            continue

    return resultados


if __name__ == "__main__":
    animes = [
        {
            "nombre": "Otome Kaijuu Carameliser",
            "episodio_actual": 10,
            "episodios_totales": 12,
            "pendientes": 1,
            "episodio_buscado": 11
        },
        {
            "nombre": "Super no Ura de Yani Suu Futaria",
            "episodio_actual": 9,
            "episodios_totales": 12,
            "pendientes": 1,
            "episodio_buscado": 10
        }
    ]

    driver = configurar_navegador(DOWNLOAD_DIR, visor=True)

    try:
        descargados = []

        for anime in animes:
            nombre_anime = anime['nombre']
            episodio_buscado = anime['episodio_buscado']

            print(f"\n============================================================")
            print(
                f"🔎 Procesando: {nombre_anime} | Episodio: {episodio_buscado}")
            print(f"============================================================")

            #resultado = buscar_pagina_principal(driver, URL_TIOANIME, anime)
            resultado = buscar_y_obtener_url_anime(driver, anime["nombre"])

        if resultado:
            for item in resultado:
                url_episodio = item.get('enlace')

                # Extraer todos los enlaces de descarga disponibles
                links_descarga = (
                    buscar_boton_descarga(driver, url_episodio) if url_episodio else []
                )

                # Definir los servidores requeridos
                servidores_permitidos = ['voe', 'doodstream', 'mixdrop']

                # Filtrar conservando únicamente Voe, Doodstream y Mixdrop
                links_filtrados = (
                    [
                        d
                        for d in links_descarga
                        if d.get('servidor', '').lower() in servidores_permitidos
                    ]
                    if links_descarga
                    else []
                )

                # Estructura limpia con los servidores seleccionados
                item_estructurado = {
                    "nombre": item.get('nombre', nombre_anime),
                    "nombre_anime": nombre_anime,
                    "enlace": url_episodio,
                    "episodio": item.get('episodio', episodio_buscado),
                    "episodio_buscado": episodio_buscado,
                    "fuente": "JKAnime",
                    "links_descarga": links_filtrados,
                }

                descargados.append(item_estructurado)
        else:
            logging.info(f"ℹ️ No encontrado en página principal: {nombre_anime}")
    finally:
        try:
            driver.quit()
            print("\n🔒 Driver principal cerrado correctamente.")
        except Exception as e:
            print(f"⚠️ Error al cerrar el driver: {e}")
            
    now = datetime.now().strftime("%H:%M:%S")

    cant_res = len(resultado) if resultado else 0
    cant_desc = len(descargados) if descargados else 0

    print(
        f"[{now}] 📊 RESULTADOS ({cant_res}):\n{json.dumps(resultado, indent=2, ensure_ascii=False)}"
    )
    print(
        f"[{now}] 📥 DESCARGADOS ({cant_desc}):\n{json.dumps(descargados, indent=2, ensure_ascii=False)}"
    )
    '''
    # Ejecutar tu función tal como la tienes definida
    if descargados:
        videos_finales = proceso_nube_buscar_y_guardar_sheets(
            DOWNLOAD_DIR, descargados)
    else:
        logging.error("❌ No hay elementos para procesar en la nube.")
    '''
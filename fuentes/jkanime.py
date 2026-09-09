
#from config import DOWNLOAD_DIR
from utilidades.navegador import configurar_navegador
import re
import logging
import unicodedata
import difflib
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from utilidades.archivos import normalizar_nombre
from animes.comparador import tomar_captura_express


# pruebas_tioanime.py


URL_TIOANIME = "https://jkanime.net/"


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

# BUSCADOR EN PAGINA PRINCIPAL


def buscar_pagina_principal(url, animes, max_intentos=3):
    """
    Busca los animes analizando la página principal con BeautifulSoup (requests),
    validando las URLs por su estructura de episodio.
    """
    try:
        max_intentos = int(max_intentos)
    except (ValueError, TypeError):
        max_intentos = 3

    intentos = 0
    html_contenido = None
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    while intentos < max_intentos:
        try:
            print(f"🌐 Conectando a la URL mediante requests: {url}")
            response = requests.get(url, headers=headers, timeout=15)
            
            tomar_captura_express(
                url=url, 
                nombre_fuente="JKanime", 
                nombre_anime=animes["nombre"], 
                episodio=animes["episodio_buscado"]
            )

            if response.status_code == 200:
                html_contenido = response.text
                break
            else:
                print(f"⚠️ Código de estado HTTP inesperado: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Error al conectar con requests (Intento {intentos + 1}/{max_intentos}): {e}")
        
        intentos += 1
        if intentos < max_intentos:
            time.sleep(3)
        else:
            print("❌ Se agotaron los reintentos de conexión.")
            return []

    if not html_contenido:
        return []

    # Parsear el HTML con BeautifulSoup
    soup = BeautifulSoup(html_contenido, 'html.parser')
    tarjetas = soup.select("div.card")
    print(f"🔍 Total de tarjetas 'div.card' encontradas en el HTML: {len(tarjetas)}")

    if len(tarjetas) == 0:
        print("⚠️ Advertencia: No se encontraron elementos 'div.card'.")
        return []

    videos_encontrados = []

    for index, tarjeta in enumerate(tarjetas):
        try:
            enlace_tag = tarjeta.select_one("a[href]")
            if not enlace_tag:
                continue
            
            href = enlace_tag.get("href")
            url_completa = urljoin(url, href)

            # Extraer el episodio primero; si la URL no tiene formato de episodio, se omite
            episodio = extraer_episodio_desde_url(url_completa)
            if episodio is None:
                try:
                    badge_tag = tarjeta.select_one("span.badge-primary")
                    if badge_tag:
                        match_ep = re.search(r'\d+', badge_tag.text)
                        if match_ep:
                            episodio = int(match_ep.group())
                except Exception:
                    pass

            if episodio is None:
                continue

            texto = ""
            try:
                titulo_tag = tarjeta.select_one("h5.strlimit")
                if titulo_tag:
                    texto = titulo_tag.get_text(strip=True)
            except Exception:
                pass

            if not texto:
                partes_url = [p for p in url_completa.split("/") if p]
                if len(partes_url) >= 2:
                    slug_anime = partes_url[-2]
                    texto = slug_anime.replace("-", " ").title()

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

        # 1. Bucle para asegurar el clic hasta que la tabla aparezca visible en el DOM
        tabla_visible = False
        intentos = 0
        max_intentos = 5

        while not tabla_visible and intentos < max_intentos:
            intentos += 1
            try:
                boton_dwld = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "div#dwld, .player-btn[id='dwld']"))
                )
                driver.execute_script("arguments[0].click();", boton_dwld)
                # Breve pausa para la animación y posible apertura de anuncio
                time.sleep(1.5)

                # 🛡️ Cerrar pestañas de anuncios generadas en cada intento de clic
                if len(driver.window_handles) > 1:
                    for handle in driver.window_handles:
                        if handle != ventana_principal:
                            driver.switch_to.window(handle)
                            driver.close()
                    driver.switch_to.window(ventana_principal)

                # Verificar si la tabla ya es visible y contiene filas de datos
                tabla = driver.find_element(By.CSS_SELECTOR, "table")
                if tabla.is_displayed():
                    filas = tabla.find_elements(By.CSS_SELECTOR, "tbody tr")
                    if len(filas) > 1:
                        tabla_visible = True
            except Exception:
                # Si falla el intento, reintentar en el siguiente ciclo del bucle
                time.sleep(1)

        if not tabla_visible:
            print(
                f"❌ No se pudo desplegar la tabla de servidores tras {max_intentos} intentos en {video_url}")
            return None

        # 2. Localizar y extraer los datos de la tabla confirmada
        tabla_servidores = driver.find_element(By.CSS_SELECTOR, "table")
        filas = tabla_servidores.find_elements(By.CSS_SELECTOR, "tbody tr")

        links_descarga = []
        for fila in filas[1:]:  # Omitir la primera fila de encabezados
            columnas = fila.find_elements(By.TAG_NAME, "td")
            if len(columnas) >= 4:
                servidor = columnas[0].text.strip()
                tamano = columnas[1].text.strip()
                audio = columnas[2].text.strip()

                link_tag = columnas[3].find_element(By.TAG_NAME, "a")
                url_descarga = link_tag.get_attribute("href")

                links_descarga.append({
                    "servidor": servidor,
                    "tamano": tamano,
                    "audio": audio,
                    "enlace": url_descarga
                })

        if links_descarga:
            print(
                f"✅ Se extrajeron {len(links_descarga)} enlaces de descarga de {video_url}")
            return links_descarga
        else:
            print(f"⚠️ La tabla está vacía para {video_url}")
            return None

    except Exception as e:
        try:
            if len(driver.window_handles) > 1:
                for handle in driver.window_handles:
                    if handle != driver.current_window_handle:
                        driver.switch_to.window(handle)
                        driver.close()
                driver.switch_to.window(driver.current_window_handle)
        except:
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


def buscar_videos_jkanime(driver, url, animes):

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

                # Filtrar servidores de interés
                descargas_filtradas = [
                    d for d in links_descarga
                    if d['servidor'].lower() in ['mediafire', 'mega']
                ] if links_descarga else []

                # 2. Selección automática: Buscar Mega primero, si no existe, buscar Mediafire
                enlace_principal = None

                # Si no hay Mega, buscar Mediafire como respaldo
                if not enlace_principal:
                    for d in descargas_filtradas:
                        if d['servidor'].lower() == 'mediafire':
                            enlace_principal = d['enlace']
                            break

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
                    "fuente": "JKAnime",
                    # <--- Aquí va el enlace seleccionado automáticamente
                    "link_descarga": enlace_principal,
                }

                resultados.append(item_estructurado)
            else:
                logging.info(
                    f"ℹ️ No encontrado en página principal: {nombre_anime}")
            continue


    return resultados


'''
if __name__ == "__main__":
    animes = [
        {
            "nombre": "World Is Dancing",
            "episodio_actual": 10,
            "episodios_totales": 12,
            "pendientes": 1,
            "episodio_buscado": 11
        },
        {
            "nombre": "Toumei na Yoru ni Kakeru Kimi to, Me ni Mienai Koi wo Shita",
            "episodio_actual": 9,
            "episodios_totales": 12,
            "pendientes": 1,
            "episodio_buscado": 10
        }
    ]

    driver = configurar_navegador(DOWNLOAD_DIR)

    try:
        descargados = []

        for anime in animes:
            nombre_anime = anime['nombre']
            episodio_buscado = anime['episodio_buscado']

            print(f"\n============================================================")
            print(
                f"🔎 Procesando: {nombre_anime} | Episodio: {episodio_buscado}")
            print(f"============================================================")

            resultado = buscar_pagina_principal(driver, URL_TIOANIME, anime)

            if resultado:
                for item in resultado:
                    url_episodio = item.get('enlace')
                    links_descarga = buscar_boton_descarga(
                        driver, url_episodio) if url_episodio else []

                    # Filtrar servidores de interés
                    descargas_filtradas = [
                        d for d in links_descarga
                        if d['servidor'].lower() in ['mediafire', 'mega']
                    ] if links_descarga else []

                    # 2. Selección automática: Buscar Mega primero, si no existe, buscar Mediafire
                    enlace_principal = None

                    # Intentar encontrar Mega
                    for d in descargas_filtradas:
                        if d['servidor'].lower() == 'mega':
                            enlace_principal = d['enlace']
                            break

                    # Si no hay Mega, buscar Mediafire como respaldo
                    if not enlace_principal:
                        for d in descargas_filtradas:
                            if d['servidor'].lower() == 'mediafire':
                                enlace_principal = d['enlace']
                                break

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
                        "fuente": "JKAnime",
                        # <--- Aquí va el enlace seleccionado automáticamente
                        "link_descarga": enlace_principal,
                    }

                    descargados.append(item_estructurado)
            else:
                logging.info(
                    f"ℹ️ No encontrado en página principal: {nombre_anime}")

    finally:
        try:
            driver.quit()
            print("\n🔒 Driver principal cerrado correctamente.")
        except Exception as e:
            print(f"⚠️ Error al cerrar el driver: {e}")

    # Ejecutar tu función tal como la tienes definida
    if descargados:
        videos_finales = proceso_nube_buscar_y_guardar_sheets(
            DOWNLOAD_DIR, descargados)
    else:
        logging.error("❌ No hay elementos para procesar en la nube.")
'''
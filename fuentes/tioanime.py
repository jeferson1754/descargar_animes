import requests
import time
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import difflib
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utilidades.archivos import normalizar_nombre


def extraer_episodio_desde_url(url):
    match = re.search(r'-(\d+)$', url)

    if match:
        return int(match.group(1))

    return None


def buscar_pagina_principal(url, animes, max_intentos=3):
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

            print(
                f"⚠️ Error al conectar con la página "
                f"(Intento {intentos}/{max_intentos}): {e}"
            )

            if intentos < max_intentos:

                print(
                    "🔄 Reintentando en 3 segundos..."
                )

                time.sleep(3)

            else:

                print(
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

            for anime in animes:

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
                    print(
                        f"⚠️ No se pudo determinar el episodio de: "
                        f"{url_completa}"
                    )
                    continue

                if episodio != episodio_buscado:
                    print(
                        f"⏭️ Episodio incorrecto: {episodio}. "
                        f"Se necesita el episodio {episodio_buscado}."
                    )
                    continue

                print(
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
                    "episodio_buscado": anime.get(
                        "episodio_buscado"
                    )
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

        print(
            f"❌ Error al procesar el contenido HTML: {e}"
        )

        return []

def buscar_videos_tioanime(url, nombres_videos):
    """
    Función principal para buscar videos en TioAnime.
    """
    print(f"🔍 Buscando videos en: {url}")
    return buscar_pagina_principal(url, nombres_videos)


def obtener_ultimo_episodio(driver, url_anime, episodio_buscado=None):
    print(f"📺 Consultando episodios: {url_anime}")

    driver.get(url_anime)

    try:
        elementos = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located(
                (
                    By.CSS_SELECTOR,
                    "a.fa-play-circle"
                )
            )
        )

        episodios = []

        for elemento in elementos:

            texto = elemento.text.strip()

            match = re.search(
                r"Episodio\s+(\d+)",
                texto,
                re.IGNORECASE
            )

            if not match:
                continue

            numero = int(match.group(1))

            enlace = elemento.get_attribute("href")

            episodios.append({
                "episodio": numero,
                "url": enlace
            })

            print(
                f"🎬 Episodio {numero}: {enlace}"
            )

        if not episodios:
            print("❌ No se encontraron episodios.")
            return None

        ultimo = max(
            episodios,
            key=lambda x: x["episodio"]
        )

        print(
            f"✅ Último episodio encontrado: "
            f"{ultimo['episodio']}"
        )

        print(
            f"🔗 URL: {ultimo['url']}"
        )

        return ultimo

    except Exception as e:

        print(
            f"❌ Error obteniendo episodios: {e}"
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
            print(f"No se encontró el botón de descarga en {video_url}")
            return None

    except Exception as e:
        print(f"Error al acceder a {video_url}: {e}")
        return None

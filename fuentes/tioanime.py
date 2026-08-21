import requests
import time
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import difflib
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def extraer_episodio_desde_url(url):
    match = re.search(r'-(\d+)$', url)

    if match:
        return int(match.group(1))

    return None


def buscar_pagina_principal(url, nombres_videos, max_intentos=3):
    """
    Busca videos en la página web con un sistema de reintentos en caso de fallo de conexión.
    """
    intentos = 0

    while intentos < max_intentos:
        try:
            # Intentar obtener el contenido de la página web
            # Añadido timeout para evitar bloqueos largos
            respuesta = requests.get(url, timeout=10)
            respuesta.raise_for_status()  # Verifica si la solicitud fue exitosa

            # Si la conexión es exitosa, rompemos el bucle de reintentos
            break

        except requests.exceptions.RequestException as e:
            intentos += 1
            print(
                f"⚠️ Error al conectar con la página (Intento {intentos}/{max_intentos}): {e}")

            if intentos < max_intentos:
                print("🔄 Reintentando en 3 segundos...")
                time.sleep(3)
            else:
                print("❌ Se agotaron los reintentos. No se pudo conectar con la página.")
                return []

    # Si pasamos los intentos con éxito, procesamos el contenido con BeautifulSoup
    try:
        soup = BeautifulSoup(respuesta.text, 'html.parser')

        # Lista para almacenar los enlaces de los videos encontrados
        videos_encontrados = []

        # Función para normalizar el nombre (eliminar caracteres especiales y convertir a minúsculas)
        def normalizar_nombre(nombre):
            return re.sub(r'\s*:\s*', ':', nombre).lower()

        # Buscar todos los enlaces en la página
        for enlace in soup.find_all('a', href=True):
            texto = enlace.text.strip()
            href = enlace['href']

            # Unir la URL base con el enlace relativo
            url_completa = urljoin(url, href)

            # Verificar si el enlace pertenece al formato "https://tioanime.com/ver/(nombre_anime)"
            if "https://tioanime.com/ver/" in url_completa:
                for nombre in nombres_videos:
                    # Normalizar tanto el nombre del anime como el texto del enlace
                    nombre_normalizado = normalizar_nombre(nombre)
                    texto_normalizado = normalizar_nombre(texto)

                    coincidencias = difflib.get_close_matches(
                        nombre_normalizado, [texto_normalizado], n=1, cutoff=0.7)

                    if coincidencias:
                        # Evitar duplicados si un anime ya fue agregado
                        nuevo_video = {'nombre': texto, 'enlace': url_completa,
                                       'episodio': extraer_episodio_desde_url(url_completa)}
                        if nuevo_video not in videos_encontrados:
                            videos_encontrados.append(nuevo_video)

        return videos_encontrados

    except Exception as e:
        print(f"❌ Error al procesar el contenido HTML: {e}")
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

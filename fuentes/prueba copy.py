# pruebas_tioanime.py
from config import DOWNLOAD_DIR
from utilidades.navegador import configurar_navegador
import re
import unicodedata
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

URL_TIOANIME = "https://tioanime.com/"


def buscar_y_obtener_url_anime(driver, nombre_anime):
    try:
        print(f"🔍 Buscando en la web de TioAnime: {nombre_anime}")
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
            print("⏳ Buscando en el menú desplegable...")
            primer_resultado = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div#search-results a.anime, div#search-results a"))
            )
            href_relativo = primer_resultado.get_attribute("href")

            if href_relativo and "javascript" not in href_relativo and "#" not in href_relativo:
                print(f"✅ ¡Encontrado en el desplegable! URL: {href_relativo}")
                return href_relativo
        except:
            print(
                "⚠️ El menú desplegable no respondió. Enviando tecla ENTER por seguridad...")

        # 5. Respaldo por ENTER si el desplegable falla
        input_buscador.send_keys(Keys.ENTER)
        time.sleep(3)

        primer_resultado_directorio = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "article.anime a, .anime-grid a"))
        )
        href_relativo = primer_resultado_directorio.get_attribute("href")

        print(f"✅ ¡Encontrado por redirección! URL: {href_relativo}")
        return href_relativo

    except Exception as e:
        print(
            f"❌ No se pudo encontrar el anime '{nombre_anime}' de ninguna forma: {e}")
        return None


if __name__ == "__main__":
    animes = [
        {
            "nombre": "Grow Up Show: Himawari no Circus-dan",
            "episodio_actual": 6,
            "episodios_totales": 12,
            "pendientes": 2,
            "episodio_buscado": 7
        },
        {
            "nombre": "Mairimashita! Iruma-kun 4th Season",
            "episodio_actual": 18,
            "episodios_totales": 24,
            "pendientes": 2,
            "episodio_buscado": 19
        },
        {
            "nombre": "Honzuki no Gekokujou: Shisho ni Naru Tame ni wa Shudan wo Erandeiraremasen 4th Season",
           "episodio_actual": 17,
            "episodios_totales": 24,
            "pendientes": 2,
            "episodio_buscado": 18
        }
    ]

    # Configuramos el navegador una sola vez fuera del bucle para ahorrar recursos
    driver = configurar_navegador(DOWNLOAD_DIR)

    try:
        # 🔄 Bucle for para recorrer cada anime de tu lista
        for anime in animes:
            nombre_anime = anime['nombre']
            episodio_buscado = anime['episodio_buscado']

            print(f"\n============================================================")
            print(
                f"🔎 Procesando: {nombre_anime} | Episodio: {episodio_buscado}")
            print(f"============================================================")

            # 1. Buscamos y obtenemos la URL general del anime
            enlace_anime = buscar_y_obtener_url_anime(driver, nombre_anime)

            if enlace_anime:
                print(f"🌐 URL obtenida: {enlace_anime}")

                # ---------------------------------------------------------
                # AQUÍ LLAMARÁS A TU FUNCIÓN QUE ENTRA A LA URL DEL ANIME,
                # BUSCA EL EPISODIO ESPECÍFICO Y OBTIENE EL LINK DE MEGA.
                # Ej: enlace_descarga = buscar_episodio_y_descarga(driver, enlace_anime, episodio_buscado)
                # ---------------------------------------------------------

            else:
                print(
                    f"❌ No se pudo procesar {nombre_anime} porque no se encontró la URL.")

    finally:
        # Aseguramos que el navegador se cierre al terminar todos los procesos
        try:
            driver.quit()
            print("\n🔒 Driver cerrado correctamente.")
        except Exception as e:
            print(f"⚠️ Error al cerrar el driver: {e}")

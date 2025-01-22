from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import os


def configurar_navegador(download_dir):
    # Configurar opciones de Chrome
    chrome_options = Options()

    prefs = {
        # Ruta donde se guardarán los archivos descargados
        "download.default_directory": download_dir,
        # Desactiva el aviso de confirmación de descarga
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True  # Asegura que no se bloqueen descargas
    }

    chrome_options.add_experimental_option("prefs", prefs)

    # Ejecuta en modo headless (sin interfaz gráfica)
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=800,600")

    # Iniciar el navegador
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def leer_nombres_y_enlaces_desde_txt(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            contenido = file.read()

        # Utilizar expresiones regulares para extraer los nombres y enlaces
        videos = []
        patrones = re.findall(
            r'"nombre": "(.*?)".*?"link_video": "(.*?)".*?"link_descarga": "(.*?)"', contenido, re.DOTALL)

        for match in patrones:
            nombre, enlace_video, enlace_descarga = match
            videos.append(
                {'nombre': nombre, 'link_video': enlace_video, 'link_descarga': enlace_descarga})

        print(f"Videos leídos desde el archivo: {videos}")
        return videos

    except FileNotFoundError:
        print(f"El archivo '{filename}' no fue encontrado.")
        return []


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


def hacer_click_en_boton_descarga(driver, enlace_descarga, download_dir, nombre_video):
    """Hace clic en el botón de descarga y espera que el archivo se descargue."""
    try:
        # Accede al enlace de descarga
        driver.get(enlace_descarga)

        # Espera a que el botón de descarga sea clickeable y hace clic en él
        boton_descarga = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".mega-button.positive.js-default-download.js-standard-download"))
        )

        # Hacer clic en el botón de descarga
        boton_descarga.click()
        print(f"Descargando archivo para: {nombre_video}")

        # Esperar a que la descarga se complete
        archivo_descargado = verificar_archivo_reciente(
            download_dir, nombre_video)
        print(f"Archivo descargado: {archivo_descargado}")

    except Exception as e:
        print(f"Error al intentar descargar el archivo desde {enlace_descarga}: {e}")


def verificar_archivo_reciente(download_dir, nombre_video):
    print("Esperando pacientemente durante un minuto...")
    time.sleep(500)  # Espera durante 1 minuto
    print("¡Un minuto ha pasado! Ahora, podemos continuar con lo que necesites.")


# Leer los videos desde el archivo .txt
videos = leer_nombres_y_enlaces_desde_txt("resultados_link.txt")


download_dir = r"C:\Users\jvargas\Phyton\Descargar_Videos\descargas"

# Iniciar el navegador
driver = configurar_navegador(download_dir)

# Lista para almacenar los videos con enlaces de descarga
videos_con_enlace = []

# Buscar los botones de descarga para cada video
for video in videos:
    print(f"Buscando enlace de descarga para: {video['nombre']}")
    enlace_descarga = buscar_boton_descarga(driver, video['link_video'])

    if enlace_descarga:
        video['link_descarga'] = enlace_descarga
        videos_con_enlace.append(video)
        # Hacer clic en el botón de descarga y esperar la descarga
        hacer_click_en_boton_descarga(
            driver, enlace_descarga, download_dir, video['nombre'])


# Finalizar el navegador
driver.quit()

print("Datos guardados en 'resultados_descarga.txt'")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import requests
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


def extraer_nombres_anime(url, download_dir):
    driver = configurar_navegador(download_dir)
    driver.get(url)

    # Espera que la página se cargue
    time.sleep(5)  # Ajusta el tiempo según sea necesario

    # Buscar todas las celdas con la clase "fw-500"
    elementos = driver.find_elements(By.CSS_SELECTOR, "td.fw-500")

    # Extraer los nombres de anime
    nombres_anime = [elemento.text.strip() for elemento in elementos]

    driver.quit()
    return nombres_anime


def guardar_resultados_animes_txt(nombres, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        # Escribir los nombres de los animes
        for nombre in nombres:
            file.write(f"{nombre}\n")


def leer_nombres_desde_txt(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            # Leer las líneas y eliminar las líneas vacías o las líneas que no contienen datos relevantes
            nombres = [line.strip()
                       for line in file.readlines() if line.strip()]
        return nombres
    except FileNotFoundError:
        print(f"El archivo '{filename}' no fue encontrado.")
        return []


def buscar_videos(url, nombres_videos):
    try:
        # Obtener el contenido de la página web
        respuesta = requests.get(url)
        respuesta.raise_for_status()  # Verifica si la solicitud fue exitosa
        soup = BeautifulSoup(respuesta.text, 'html.parser')

        # Lista para almacenar los enlaces de los videos encontrados
        videos_encontrados = []

        # Buscar todos los enlaces en la página
        for enlace in soup.find_all('a', href=True):
            texto = enlace.text.strip()
            href = enlace['href']

            # Unir la URL base con el enlace relativo
            url_completa = urljoin(url, href)

            # Verificar si el enlace pertenece al formato "https://tioanime.com/ver/(nombre_anime)"
            if "https://tioanime.com/ver/" in url_completa:
                for nombre in nombres_videos:
                    if nombre.lower() in texto.lower():  # Comparar ignorando mayúsculas y minúsculas
                        videos_encontrados.append({
                            'nombre': texto,
                            'enlace': url_completa
                        })

        return videos_encontrados

    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la página: {e}")
        return []


def guardar_resultados_videos_txt(videos, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        # Escribir el conteo de videos encontrados
        file.write(f"Cantidad de videos encontrados: {len(videos)}\n\n")

        # Escribir los detalles de cada video
        for video in videos:
            file.write(f'"nombre": "{video["nombre"]}",\n')
            file.write(
                f'"link_video": "{video["enlace"]}"\n')
            file.write("-" * 40 + "\n")


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


def confirmar_descarga(nombres_animes):
    print("\nHay estos animes disponibles para descargar:")
    for idx, nombre in enumerate(nombres_animes, 1):
        print(f"{idx}. {nombre}")

    while True:
        respuesta = input(
            "\n¿Quieres comenzar a descargar estos animes? (Y/N): ").strip().lower()
        if respuesta == 'y':
            print("Iniciando la descarga...")
            return True
        elif respuesta == 'n':
            print("Descarga cancelada.")
            return False
        else:
            print("Por favor, responde con 'Y' (sí) o 'N' (no).")


def verificar_si_descargado(nombres_animes, download_dir):
    """
    Verifica si un archivo con el nombre del anime ya está descargado en el directorio especificado.
    Compara el nombre del anime con los archivos presentes en la carpeta de descargas.

    Args:
    - nombre_anime (str): El nombre del anime a buscar.
    - download_dir (str): El directorio donde se descargan los archivos.

    Returns:
    - bool: True si el archivo ya está descargado, False si no.
    """
    # Convertir el nombre del anime a minúsculas para hacer una comparación insensible a mayúsculas
    no_descargados = []

    print("\nVerificando el estado de los animes en el directorio de descargas...")

    # Listar los archivos en el directorio de descargas
    archivos_descargados = os.listdir(download_dir)

    for nombre in nombres_animes:
        # Convertir el nombre del anime a minúsculas para hacer una comparación insensible a mayúsculas
        nombre_anime_lower = nombre.lower()
        encontrado = False

        # Comprobar si algún archivo en el directorio contiene el nombre del anime
        for archivo in archivos_descargados:
            if nombre_anime_lower in archivo.lower() and archivo.endswith(".mp4"):
                print(f"✅ El anime '{
                      nombre}' ya está descargado como '{archivo}'.")
                encontrado = True
                break  # Salir del bucle interno si se encuentra el archivo

        if not encontrado:
            print(f"❌ El anime '{nombre}' no ha sido descargado aún.")
            no_descargados.append(nombre)

    return no_descargados


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


def flujo_descarga_animes(file_name, download_dir):
    """
     Gestiona el proceso de búsqueda y descarga de animes desde una lista de nombres.

     Args:
         file_name (str): Archivo .txt con los nombres de los animes.
         url_tioanime (str): URL base del sitio web de TioAnime.
         download_dir (str): Directorio donde se descargarán los videos.
     """
    # Paso 1: Leer los nombres de los animes desde el archivo .txt
    nombres_animes = leer_nombres_desde_txt(file_name)
    if not nombres_animes:
        print("El archivo no contiene nombres de animes.")
        return

        # Paso 2: Buscar videos relacionados con los nombres de animes
    print("Buscando videos relacionados con los nombres indicados...")
    videos_encontrados = buscar_videos(url_tioanime, nombres_animes)

    if not videos_encontrados:
        print("No se encontraron videos relacionados con los animes indicados.")
        return

        # Paso 3: Guardar los resultados de videos encontrados
    guardar_resultados_videos_txt(
        videos_encontrados, "resultados_videos.txt")

    # Leer los nombres de los videos desde el archivo de resultados
    videos_animes = leer_nombres_desde_txt("resultados_videos.txt")
    if not videos_animes:
        print("No se encontraron nombres de videos para descargar.")
        return

        # Paso 4: Verificar si los animes ya están descargados
    print("Verificando si los animes ya están descargados...")
    animes_no_descargados = verificar_si_descargado(
        videos_animes, download_dir)

    if not animes_no_descargados:
        print("\nTodos los animes ya han sido descargados.")
        return

        # Paso 5: Confirmar si el usuario quiere descargar los animes no descargados
    print("\nEstos animes no están descargados y estarán disponibles para la descarga:")
    for idx, anime in enumerate(animes_no_descargados, 1):
        print(f"{idx}. {anime}")

    if not confirmar_descarga(animes_no_descargados):
        print("El usuario canceló la descarga.")
        return

    driver = configurar_navegador(download_dir)

    for video in videos_encontrados:
        print(f"Buscando enlace de descarga para: {video['nombre']}")
        enlace_descarga = buscar_boton_descarga(
            driver, f"{video['enlace']}")
        if enlace_descarga:
            print(f"Descargando: {video['nombre']}...")
            hacer_click_en_boton_descarga(
                driver, enlace_descarga, download_dir, video['nombre'])
        else:
            print(f"No se pudo encontrar el enlace de descarga para {
                  video['nombre']}.")

    driver.quit()
    print("Descargas completadas.")


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
        print(f"Error al intentar descargar el archivo desde {
              enlace_descarga}: {e}")


def verificar_archivo_reciente(download_dir, nombre_video):
    print("Esperando pacientemente durante un minuto...")
    time.sleep(500)  # Espera durante 1 minuto
    print("¡Un minuto ha pasado! Ahora, podemos continuar con lo que necesites.")


def eliminar_txt():
    """Elimina todos los archivos en formato TXT en la carpeta actual excepto 'requirements.txt' tras confirmación."""
  # Filtrar archivos .txt excluyendo 'requirements.txt'
    archivos_txt = [archivo for archivo in os.listdir(
        '.') if archivo.endswith('.txt') and archivo != 'requirements.txt']

    if not archivos_txt:
        print("No se encontraron archivos TXT en la carpeta actual (excepto 'requirements.txt').")
        return

    print("Se encontraron los siguientes TXT (excepto 'requirements.txt'):")
    for archivo in archivos_txt:
        print(archivo)

    confirmar = input(
        "¿Estás seguro de que deseas eliminar estos archivos? (Presiona Enter para confirmar): ")

    if confirmar == '':
        for archivo in archivos_txt:
            try:
                os.remove(archivo)
                print(f"Eliminado: {archivo}")
            except Exception as e:
                print(f"No se pudo eliminar {archivo}: {e}")
    else:
        print("Eliminación cancelada.")


if __name__ == "__main__":

    download_dir = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"

    # URL de la página a analizar
    url = "https://inventarioncc.infinityfreeapp.com/Anime/Emision/?enviar=&accion=HOY"

    # Extraer y mostrar los nombres de los animes
    nombres_anime = extraer_nombres_anime(url, download_dir)

    # Guardar los nombres en un archivo .txt
    guardar_resultados_animes_txt(nombres_anime, "resultados_anime.txt")

    # Mostrar conteo y los nombres en la consola
    conteo_anime = len(nombres_anime)

    print(f"Cantidad de animes extraídos: {conteo_anime}")
    for nombre in nombres_anime:
        print(nombre)

    print(f"Datos guardados en 'resultados_anime.txt'")

    # URL de la página web
    url_tioanime = "https://tioanime.com/"

    flujo_descarga_animes("resultados_anime.txt", download_dir)

    eliminar_txt()

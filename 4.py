from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import difflib
import requests
import time
import re
import os


def configurar_navegador(download_dir):
    chrome_options = webdriver.ChromeOptions()

    # Opciones para evitar errores
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")

    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--allow-insecure-localhost')
    chrome_options.add_argument('--ignore-ssl-errors=yes')

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=800,600")
    chrome_options.add_argument("--headless")  # si lo deseas sin interfaz

    # Configuración de descarga
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    # Lista de versiones de ChromeDriver a probar (de más nueva a más vieja)
    versiones_a_probar = [
        "136.0.7103.114",  # Tu versión actual que funciona
        "135.0.7035.122",  # Versiones anteriores como respaldo
        "134.0.6847.140",
        "133.0.6835.106",
        "132.0.6834.110"
    ]

    # Intentar cada versión hasta encontrar una que funcione
    for version in versiones_a_probar:
        try:
            print(f"Intentando ChromeDriver versión {version}...")
            driver_path = ChromeDriverManager(driver_version=version).install()
            print(f"ChromeDriver {version} instalado en: {driver_path}")

            # Probar inicializar el navegador
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"✓ ChromeDriver {version} funcionando correctamente")
            return driver

        except Exception as e:
            print(f"✗ ChromeDriver {version} falló: {str(e)[:100]}...")
            continue

    # Si ninguna versión funciona, usar webdriver-manager automático
    try:
        print("Intentando con detección automática de versión...")
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path)
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error final: {e}")
        print("\n=== SOLUCIÓN MANUAL ===")
        print("1. Ve a: https://googlechromelabs.github.io/chrome-for-testing/")
        print("2. Descarga ChromeDriver compatible con tu versión de Chrome")
        print("3. Guárdalo en una carpeta y actualiza la ruta en el código")
        sys.exit(1)


def obtener_version_chrome():
    """Obtiene la versión de Chrome instalada en el sistema"""
    try:
        import subprocess
        import json

        # Obtener versión de Chrome en Windows
        result = subprocess.run([
            'reg', 'query',
            'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon',
            '/v', 'version'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            version = result.stdout.split()[-1]
            return version

        # Método alternativo
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome_path):
            result = subprocess.run(
                [chrome_path, '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.split()[-1]
                return version

    except Exception as e:
        print(f"No se pudo detectar la versión de Chrome: {e}")

    return None


def configurar_navegador_inteligente(download_dir):
    """Versión inteligente que detecta la versión de Chrome automáticamente"""

    # Detectar versión de Chrome
    version_chrome = obtener_version_chrome()
    if version_chrome:
        print(f"Chrome detectado: versión {version_chrome}")
        version_major = version_chrome.split('.')[0]

        # Mapear versiones principales a ChromeDriver compatibles
        version_map = {
            "136": ["136.0.7103.114", "135.0.7035.122"],
            "135": ["135.0.7035.122", "134.0.6847.140"],
            "134": ["134.0.6847.140", "133.0.6835.106"],
            "133": ["133.0.6835.106", "132.0.6834.110"],
            "132": ["132.0.6834.110", "131.0.6778.87"]
        }

        versiones_compatibles = version_map.get(
            version_major, ["136.0.7103.114"])
        print(f"Versiones de ChromeDriver a probar: {versiones_compatibles}")
    else:
        print("No se pudo detectar Chrome, usando versiones por defecto")
        versiones_compatibles = ["136.0.7103.114", "135.0.7035.122"]

    chrome_options = webdriver.ChromeOptions()

    # Opciones
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")

    # Configuración de descarga
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    # Probar versiones compatibles
    for version in versiones_compatibles:
        try:
            print(f"Probando ChromeDriver {version}...")
            driver_path = ChromeDriverManager(driver_version=version).install()
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"✓ Éxito con ChromeDriver {version}")
            return driver
        except Exception as e:
            print(f"✗ Falló ChromeDriver {version}")
            continue

    # Fallback
    return configurar_navegador(download_dir)


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


def normalizar_nombre(nombre):
    """
    Normaliza el nombre del anime para que sea comparable con los nombres de archivo.
    Elimina los espacios y caracteres no alfabéticos y convierte a minúsculas.

    Args:
        nombre (str): Nombre del anime a normalizar.

    Returns:
        str: Nombre normalizado del anime.
    """
    # Eliminar espacios, guiones, guiones bajos y convertir a minúsculas
    nombre_normalizado = re.sub(r'[^a-zA-Z0-9]', '', nombre.lower())
    return nombre_normalizado


def obtener_archivos_descargados(download_dir):
    """
    Obtiene una lista de los archivos descargados en el directorio de descargas.

    Args:
        download_dir (str): Directorio de descargas.

    Returns:
        list: Lista de nombres de archivos en el directorio de descargas.
    """
    try:
        archivos_descargados = os.listdir(download_dir)
        archivos_mp4 = [
            archivo for archivo in archivos_descargados if archivo.endswith(".mp4")]
        return archivos_mp4
    except FileNotFoundError:
        print("El directorio de descargas no se encontró.")
        return []


def leer_nombres_animes_a_descargar(archivo_animes):
    """
    Lee los nombres de los animes a descargar desde un archivo.

    Args:
        archivo_animes (str): Nombre del archivo que contiene los animes a descargar.

    Returns:
        list: Lista de nombres de los animes.
    """
    try:
        with open(archivo_animes, 'r', encoding='utf-8') as f:
            animes = [linea.strip() for linea in f.readlines()]
        return animes
    except FileNotFoundError:
        print(f"No se pudo encontrar el archivo {archivo_animes}.")
        return []


def comparar_descargas(animes_a_descargar, archivos_descargados):
    """
    Compara los animes a descargar con los archivos descargados para evitar duplicados.

    Args:
        animes_a_descargar (list): Lista de animes que se quieren descargar.
        archivos_descargados (list): Lista de archivos ya descargados.

    Returns:
        list: Lista de animes que no han sido descargados.
    """
    animes_no_descargados = []
    for anime in animes_a_descargar:
        # Normalizar el nombre del anime a comparar
        anime_normalizado = normalizar_nombre(anime)

        # Comparar el nombre normalizado con los archivos descargados
        encontrado = False
        for archivo in archivos_descargados:
            archivo_normalizado = normalizar_nombre(archivo)

            # Si el nombre normalizado del anime está en el archivo descargado
            if anime_normalizado in archivo_normalizado:
                encontrado = True
                break

        if not encontrado:
            animes_no_descargados.append(anime)

    return animes_no_descargados


def guardar_archivos_descargados(archivos, archivo_salida):
    """
    Guarda los nombres de los archivos descargados en un archivo de texto.

    Args:
        archivos (list): Lista de archivos a guardar.
        archivo_salida (str): Nombre del archivo de salida donde se guardarán los nombres.
    """
    with open(archivo_salida, 'w', encoding='utf-8') as f:
        for archivo in archivos:
            f.write(archivo + "\n")


def buscar_videos(url, nombres_videos):
    try:
        # Obtener el contenido de la página web
        respuesta = requests.get(url)
        respuesta.raise_for_status()  # Verifica si la solicitud fue exitosa
        soup = BeautifulSoup(respuesta.text, 'html.parser')

        # Lista para almacenar los enlaces de los videos encontrados
        videos_encontrados = []

        # Función para normalizar el nombre (eliminar caracteres especiales y convertir a minúsculas)
        def normalizar_nombre(nombre):
            # Eliminar caracteres especiales (como ':' o cualquier otro símbolo no alfanumérico)
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
                        videos_encontrados.append(
                            {'nombre': texto, 'enlace': url_completa})

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


def guardar_animes_no_descargados(animes_no_descargados, archivo_salida):
    """
    Guarda los animes que no han sido descargados en un archivo de texto.

    Args:
        animes_no_descargados (list): Lista de animes que no se han descargado.
        archivo_salida (str): Nombre del archivo donde se guardarán los animes no descargados.
    """
    with open(archivo_salida, 'w', encoding='utf-8') as f:
        for anime in animes_no_descargados:
            f.write(anime + "\n")


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
    # Leer los videos desde el archivo .txt
    nombres_animes = leer_nombres_desde_txt(file_name)

    # Paso 3: Buscar videos relacionados con los animes
    print("Buscando videos relacionados...")
    videos_encontrados = buscar_videos(url_tioanime, nombres_animes)

    if not videos_encontrados:
        print("No se encontraron videos para los animes indicados.")
        return

    # Paso 4: Guardar resultados de videos encontrados
    guardar_resultados_videos_txt(videos_encontrados, "resultados_videos.txt")

    videos_animes = leer_nombres_desde_txt("resultados_videos.txt")

    if not videos_animes:
        print("No se encontraron nombres de animes para descargar.")
        return

    # Paso 2: Confirmar si el usuario quiere descargar
    if not confirmar_descarga(videos_animes):
        return  # Salir si el usuario no quiere proceder

    # Iniciar el navegador
    driver = configurar_navegador(download_dir)

    # Buscar los botones de descarga para cada video
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
    print("Esperando pacientemente durante dos minutos...")
    time.sleep(120)  # Espera durante 1 minuto
    print("¡Dos minutos han pasado! Ahora, podemos continuar con lo que necesites.")


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


def main(download_dir, archivo_animes, archivo_resultado_descargados, archivo_resultado_no_descargados):
    """
    Función principal que gestiona la verificación de los animes a descargar.

    Args:
        download_dir (str): Directorio de descargas.
        archivo_animes (str): Archivo de animes a descargar.
        archivo_resultado_descargados (str): Archivo donde se guardarán los archivos descargados.
        archivo_resultado_no_descargados (str): Archivo donde se guardarán los animes no descargados.
    """
    # Obtener los archivos descargados
    archivos_descargados = obtener_archivos_descargados(download_dir)

    if not archivos_descargados:
        print("No se encontraron archivos en el directorio de descargas.")
        # Asegurar que el archivo de animes no descargados se crea
        animes_a_descargar = leer_nombres_animes_a_descargar(archivo_animes)

        if not animes_a_descargar:
            print("No se encontraron animes para descargar.")
            return

        # Todos los animes en la lista de descargas se consideran no descargados
        guardar_animes_no_descargados(
            animes_a_descargar, archivo_resultado_no_descargados)
        print(f"Se ha creado el archivo {
              archivo_resultado_no_descargados} con todos los animes.")
        return

    # Guardar los archivos descargados en un archivo .txt
    guardar_archivos_descargados(
        archivos_descargados, archivo_resultado_descargados)

    # Leer los nombres de los animes a descargar
    animes_a_descargar = leer_nombres_animes_a_descargar(archivo_animes)

    if not animes_a_descargar:
        print("No se encontraron animes para descargar.")
        return

    # Comparar los animes a descargar con los archivos ya descargados
    animes_no_descargados = comparar_descargas(
        animes_a_descargar, archivos_descargados)

    if not animes_no_descargados:
        print("Todos los animes ya han sido descargados.")
    else:
        print("Animes que no han sido descargados:")
        for anime in animes_no_descargados:
            print(f"- {anime}")

    # Guardar los animes no descargados en un archivo .txt
    guardar_animes_no_descargados(
        animes_no_descargados, archivo_resultado_no_descargados)


def menu_dias():
    dias = {
        "1": "Lunes",
        "2": "Martes",
        "3": "Miércoles",
        "4": "Jueves",
        "5": "Viernes",
        "6": "Sábado",
        "7": "Domingo",
        "0": "Volver al menú principal"
    }

    while True:
        print("\n=== Seleccione un día ===")
        for clave, dia in dias.items():
            print(f"{clave}. {dia}")

        opcion_dia = input("Seleccione un día: ")

        if opcion_dia in dias:
            if opcion_dia == "0":
                return None  # Volver al menú principal
            else:
                dia_seleccionado = dias[opcion_dia]
                # Construir URL con el día seleccionado
                url = f"https://inventarioncc.infinityfreeapp.com/Anime/Emision/?dias={dia_seleccionado}&enviar2=&accion=Filtro"
                return url
        else:
            print("❌ Opción inválida. Intente de nuevo.")


def menu_principal():
    while True:
        print("\n=== MENÚ DE OPCIONES ===")
        print("1. Descargar animes de hoy")
        print("2. Descargar animes pendientes")
        print("3. Seleccionar un día")
        print("0. Salir")

        opcion = input("Seleccione una opción: ")

        if opcion == "1":
            url = "https://inventarioncc.infinityfreeapp.com/Anime/Emision/?enviar=&accion=HOY"
            return url
        elif opcion == "2":
            url = "https://inventarioncc.infinityfreeapp.com/Anime/Emision/?faltantes=&accion=HOY"
            return url
        elif opcion == "3":
            url = menu_dias()
            if url:
                return url
        elif opcion == "0":
            print("Saliendo del programa...")
            return None
        else:
            print("❌ Opción inválida. Intente de nuevo.")


def menu():

    download_dir = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"
    # download_dir = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"

    # URL de la página a analizar
    url = menu_principal()

    if url is None:
        print("No se seleccionó ninguna opción válida. Volviendo al menú principal...")

    # Extraer y mostrar los nombres de los animes
    nombres_anime = extraer_nombres_anime(url, download_dir)

    # Guardar los nombres en un archivo .txt
    guardar_resultados_animes_txt(nombres_anime, "resultados_anime.txt")

    # Mostrar conteo y los nombres en la consola
    conteo_anime = len(nombres_anime)

    # Ruta de la carpeta de descargas y archivo de animes
    archivo_animes = "resultados_anime.txt"
    archivo_resultado = "archivos_descargados.txt"
    archivo_resultado_descargados = "archivos_descargados.txt"
    archivo_resultado_no_descargados = "animes_no_descargados.txt"

    print(f"Cantidad de animes extraídos: {conteo_anime}")
    for nombre in nombres_anime:
        print(nombre)

    print(f"Datos guardados en 'resultados_anime.txt'")

    # Ejecutar la función principal
    main(download_dir, archivo_animes, archivo_resultado_descargados,
         archivo_resultado_no_descargados)

    # Ejecutar función principal solo si hay animes por descargar
    if not os.path.exists(archivo_resultado_no_descargados) or os.path.getsize(archivo_resultado_no_descargados) == 0:
        print("No se ejecuta la funcion buscar videos de anime")
    else:
        flujo_descarga_animes(archivo_resultado_no_descargados, download_dir)

    eliminar_txt()


if __name__ == "__main__":

    # URL de la página web
    url_tioanime = "https://tioanime.com/"

    menu()

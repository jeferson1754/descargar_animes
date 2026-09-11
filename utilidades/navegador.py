from selenium import webdriver
import os
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def configurar_navegador(download_dir, visor=False):
    """Configura Chrome usando Selenium Manager.

    No requiere especificar manualmente ChromeDriver.
    """
    try:
        options = webdriver.ChromeOptions()

        # -----------------------------------------
        # Opciones generales y silenciamiento de logs
        # -----------------------------------------
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--disable-notifications")

        # Evita los mensajes de error de DevTools / GPU en la consola
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        # -----------------------------------------
        # Modo Headless (Visor)
        # -----------------------------------------
        # Si visor es False (por defecto), corre oculto en segundo plano.
        # Si visor es True, abre la ventana visible del navegador.
        if not visor:
            options.add_argument("--headless=new")

        # -----------------------------------------
        # Configuración del directorio de descargas
        # -----------------------------------------
        # Crear la carpeta si no existe
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        prefs = {
            "download.default_directory": os.path.abspath(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

        # Selenium Manager se encarga del driver automáticamente
        driver = webdriver.Chrome(options=options)
        return driver

    except Exception as e:
        logging.error(f"❌ Error al configurar el navegador Chrome: {e}")
        return None
    
def configurar_navegador_inteligente(download_dir):
    """Versión inteligente que detecta la versión de Chrome automáticamente"""

    # Detectar versión de Chrome
    version_chrome = obtener_version_chrome()
    if version_chrome:
        logging.info(f"Chrome detectado: versión {version_chrome}")
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
        logging.info(f"Versiones de ChromeDriver a probar: {versiones_compatibles}")
    else:
        logging.info("No se pudo detectar Chrome, usando versiones por defecto")
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
            logging.info(f"Probando ChromeDriver {version}...")
            driver_path = ChromeDriverManager(driver_version=version).install()
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logging.info(f"✓ Éxito con ChromeDriver {version}")
            return driver
        except Exception as e:
            logging.error(f"✗ Falló ChromeDriver {version}")
            continue

    # Fallback
    return configurar_navegador(download_dir)


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
        logging.warning(f"No se pudo detectar la versión de Chrome: {e}")

    return None

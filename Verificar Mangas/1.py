from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import requests
import time
import re
import os


def configurar_navegador():
    # Configurar opciones de Chrome
    chrome_options = Options()

    # Ejecuta en modo headless (sin interfaz gráfica)
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=800,600")

    # Iniciar el navegador
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def acceder_y_guardar_urls(url, archivo_salida):
    # Asume que esta función está configurada previamente
    driver = configurar_navegador()
    driver.get(url)

    # Espera que la página se cargue
    time.sleep(5)

    # Buscar todas las etiquetas <a> dentro de <td>
    elementos = driver.find_elements(By.CSS_SELECTOR, "td a")

    # Extraer los nombres y las URLs
    nombres_y_urls = [(elemento.text.strip(), elemento.get_attribute(
        "href")) for elemento in elementos]

    # Guardar los resultados en un archivo de texto
    with open(archivo_salida, "w", encoding="utf-8") as f:
        for nombre, url in nombres_y_urls:
            f.write(
                f'"URL": "{url}"\n')
            f.write("-" * 40 + "\n")

    driver.quit()
    return nombres_y_urls


def es_url_valida(url):
    resultado = urlparse(url)
    return all([resultado.scheme, resultado.netloc])


def extraer_h2_y_td(urls_txt):
    driver = configurar_navegador()

    # Leer el archivo txt con las URLs
    with open(urls_txt, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i in range(0, len(lines), 3):
        nombre = lines[i].strip().split(":")[1].strip().strip('",')


        if es_url_valida(nombre):
            driver.get(url)
            time.sleep(3)
                # Extraer todos los h2
            h2_elementos = driver.find_elements(By.TAG_NAME, "h2")
            print(f"Se han encontrado {
                      len(h2_elementos)} títulos h2 en {url}:")
            for h2 in h2_elementos:
                    print(h2.text)
        else:
            print(f"URL no válida: {url} , Nombre: {nombre}")


    driver.quit()


if __name__ == "__main__":

    # URL de la página a analizar
    url = "https://inventarioncc.infinityfreeapp.com/Manga/?sin-actividad="

    txt = "resultados.txt"

    # Ejemplo de uso: puedes llamar a la función pasando una URL específica
    #nombres_y_urls = acceder_y_guardar_urls(url, txt)
    # Llamada a la función, pasando el archivo de texto que contiene las URLs
    extraer_h2_y_td(txt)

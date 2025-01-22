from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time


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


def extraer_nombres_anime(url):
    driver = configurar_navegador()
    driver.get(url)

    # Espera que la página se cargue
    time.sleep(5)  # Ajusta el tiempo según sea necesario

    # Buscar todas las celdas con la clase "fw-500"
    elementos = driver.find_elements(By.CSS_SELECTOR, "td.fw-500")

    # Extraer los nombres de anime
    nombres_anime = [elemento.text.strip() for elemento in elementos]

    driver.quit()
    return nombres_anime


def guardar_resultados_txt(nombres, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        # Escribir los nombres de los animes
        for nombre in nombres:
            file.write(f"{nombre}\n")


# URL de la página a analizar
url = "https://inventarioncc.infinityfreeapp.com/Anime/Emision/?enviar=&accion=HOY"

# Extraer y mostrar los nombres de los animes
nombres_anime = extraer_nombres_anime(url)

# Guardar los nombres en un archivo .txt
guardar_resultados_txt(nombres_anime, "resultados_anime.txt")

# Mostrar conteo y los nombres en la consola
conteo_anime = len(nombres_anime)

print(f"Cantidad de animes extraídos: {conteo_anime}")
for nombre in nombres_anime:
    print(nombre)

print(f"Datos guardados en 'resultados_anime.txt'")

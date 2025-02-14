from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time


def configurar_navegador():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=800,600")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def obtener_enlaces_principales(url):
    driver = configurar_navegador()
    driver.get(url)

    # Esperar a que cargue la página
    time.sleep(3)

    # Obtener todos los enlaces con clase "link" (manga)
    enlaces_manga = driver.find_elements(By.CSS_SELECTOR, "a.link")

    # Obtener todos los enlaces con clase "chart" (verificación)
    enlaces_verificacion = driver.find_elements(By.CSS_SELECTOR, "a.chart")

    # Validar que existan enlaces
    if not enlaces_manga:
        print("No se encontraron enlaces de manga.")
    if not enlaces_verificacion:
        print("No se encontraron enlaces de verificación.")

    # Recorrer los enlaces con un while
    index = 0
    while index < max(len(enlaces_manga), len(enlaces_verificacion)):
        manga = enlaces_manga[index].get_attribute(
            "href") if index < len(enlaces_manga) else "No disponible"
        verificacion = enlaces_verificacion[index].get_attribute(
            "href") if index < len(enlaces_verificacion) else "No disponible"

        print(f"[{index + 1}] Enlace del Manga: {manga}")
        print(f"[{index + 1}] Enlace de Verificación: {verificacion}")
        print("-" * 50)

        index += 1

    driver.quit()


if __name__ == "__main__":
    url = "https://inventarioncc.infinityfreeapp.com/Manga/?sin-fechas="
    obtener_enlaces_principales(url)

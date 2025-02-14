from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import re


def configurar_navegador():
    chrome_options = Options()
    # Ejecuta en modo sin interfaz gráfica
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=800,600")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def obtener_enlaces_principales(url):
    driver = configurar_navegador()
    driver.get(url)
    time.sleep(3)  # Esperar carga de la página

    # Obtener enlaces de manga y verificación
    enlaces_manga = driver.find_elements(By.CSS_SELECTOR, "a.link")
    enlaces_verificacion = driver.find_elements(By.CSS_SELECTOR, "a.chart")

    if not enlaces_manga:
        print("No se encontraron enlaces de manga.")
    if not enlaces_verificacion:
        print("No se encontraron enlaces de verificación.")

    index = 0
    while index < max(len(enlaces_manga), len(enlaces_verificacion)):
        manga = enlaces_manga[index].get_attribute(
            "href") if index < len(enlaces_manga) else "No disponible"
        verificacion = enlaces_verificacion[index].get_attribute(
            "href") if index < len(enlaces_verificacion) else "No disponible"

        print(f"\n[{index + 1}] Enlace del Manga: {manga}")
        print(f"[{index + 1}] Enlace de Verificación: {verificacion}")

        if manga and manga != "No disponible":
            extraer_fechas_manga(manga)

        print("-" * 50)
        index += 1

    driver.quit()


def extraer_fechas_manga(manga_url):
    """Abre los botones uno por uno con un lapso de 10 segundos entre cada clic y extrae todas las fechas."""
    driver = configurar_navegador()
    driver.get(manga_url)
    time.sleep(3)  # Esperar carga de la página

    # Buscar todos los botones con la clase 'btn-collapse'
    botones = driver.find_elements(By.CLASS_NAME, "btn-collapse")
    
    if botones:
        fechas = []  # Lista para almacenar las fechas extraídas
        for boton in botones:
            try:
                # Hacer clic en el botón
                boton.click()
                time.sleep(10)  # Esperar 10 segundos entre clics para cargar la información
                
                # Extraer las fechas de los elementos 'span' con clase 'badge badge-primary p-2'
                spans = driver.find_elements(By.CSS_SELECTOR, "span.badge.badge-primary.p-2")
                
                for span in spans:
                    texto = span.text.strip()  # Obtener el texto dentro del span
                    # Buscar la fecha con regex
                    fecha_match = re.search(r"\d{4}-\d{2}-\d{2}", texto)
                    if fecha_match:
                        fechas.append(fecha_match.group())  # Guardar la fecha encontrada
            except Exception as e:
                print(f"Error al intentar hacer clic o extraer fechas: {e}")

        # Mostrar todas las fechas extraídas
        if fechas:
            print("Fechas extraídas:")
            for i, fecha in enumerate(fechas, start=1):
                print(f" - [{i}] {fecha}")
        else:
            print("No se encontraron fechas en los <span>.")
    else:
        print("No se encontraron botones disponibles.")

    driver.quit()




if __name__ == "__main__":
    url = "https://inventarioncc.infinityfreeapp.com/Manga/?sin-fechas="
    obtener_enlaces_principales(url)

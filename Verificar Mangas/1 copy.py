from selenium import webdriver
from selenium.webdriver.common.by import By
import time

# Función para iniciar el WebDriver de Selenium


def iniciar_driver():
    # Si usas Chrome, asegúrate de tener el chromedriver en el PATH
    options = webdriver.ChromeOptions()
    # Para no mostrar la ventana del navegador
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    return driver

# Función para extraer datos de URLs que comienzan con "zonatmo"


def extraer_datos_zonatmo(driver, url):
    driver.get(url)

    # Aquí debes ajustar la lógica para extraer los datos que necesites de Zonatmo
    try:
        # Ejemplo: Obtener el título de la página
        titulo = driver.title
        print(f"Zonatmo - Título de la página: {titulo}")

    except Exception as e:
        print(f"Error al extraer datos de Zonatmo: {e}")

# Función para extraer el primer td de cada máximo 5 tr en URLs que comienzan con "inventario"


def extraer_datos_inventario(driver, url):
    driver.get(url)
    
    # Aquí seleccionamos todas las filas de la tabla
    try:
        filas = driver.find_elements(By.TAG_NAME, "tr")  # Encuentra todas las filas <tr>
        count = 0  # Contador para cada 5 filas

        for i, fila in enumerate(filas):
            if (i + 1) % 5 == 0:  # Extraemos datos cada 5 filas
                celdas = fila.find_elements(By.TAG_NAME, "td")  # Obtener todas las celdas <td> de la fila
                if celdas:
                    # Buscar el primer td con clase "normal"
                    for td in celdas:
                        if "normal" in td.get_attribute("class").split():
                            print(f"Inventario - Primer td con clase 'normal' en la fila {i+1}: {td.text}")
                            break  # Solo extraemos el primer td con clase 'normal'
            count += 1

    except Exception as e:
        print(f"Error al extraer datos de Inventario: {e}")


# Leer las URLs del archivo .txt


def leer_urls(archivo):
    with open(archivo, 'r') as file:
        urls = []
        for line in file:
            if '"URL":' in line:
                url = line.split('"')[3]  # Obtener la URL entre comillas
                urls.append(url)
        return urls

# Función principal para iterar sobre las URLs


def procesar_urls(archivo):
    # Iniciar el driver
    driver = iniciar_driver()

    # Leer las URLs del archivo
    urls = leer_urls(archivo)

    # Iterar sobre las URLs
    for url in urls:
        print(f"Accediendo a: {url}")
    
       #if url.startswith("https://zonatmo.com"):
            # Si la URL comienza con "zonatmo", extraemos datos específicos de Zonatmo
        #    extraer_datos_zonatmo(driver, url)
        
        if url.startswith("https://inventarioncc.infinityfreeapp.com"):
            # Si la URL comienza con "inventario", extraemos datos específicos de Inventario
            extraer_datos_inventario(driver, url)

        # Esperar 2 segundos antes de acceder a la siguiente página
        time.sleep(2)

    # Cerrar el navegador
    driver.quit()


# Ejecutar el procesamiento de URLs
if __name__ == "__main__":
    procesar_urls('urls.txt')  # Cambia 'urls.txt' por el nombre de tu archivo

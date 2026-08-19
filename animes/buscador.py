# animes/buscador.py
import time
from selenium.webdriver.common.by import By

from fuentes.tioanime import buscar_videos_tioanime
from utilidades.navegador import configurar_navegador

def extraer_nombres_anime(url, download_dir):
    
    driver = configurar_navegador(download_dir)
    
    driver.get(url)

    # Espera que la página se cargue
    time.sleep(5)

    # Buscar todas las celdas con la clase "fw-500"
    elementos = driver.find_elements(By.CSS_SELECTOR, "td.fw-500")

    nombres_limpios = []

    for elemento in elementos:
        # Usamos JavaScript para obtener SOLO el texto del nodo raíz,
        # ignorando los textos de los elementos hijos (como el span del badge)
        nombre = driver.execute_script(
            "return arguments[0].childNodes[0].textContent.trim();",
            elemento
        )

        if nombre:
            nombres_limpios.append(nombre)

    driver.quit()
    return nombres_limpios

def buscar_en_fuentes(nombres_animes, fuentes):
    """
    Busca los animes pendientes en las fuentes disponibles.

    Para cada anime:
        1. Prueba la primera fuente.
        2. Si no lo encuentra, prueba la siguiente.
        3. Devuelve los resultados encontrados.
    """

    resultados = []

    for anime in nombres_animes:

        print("\n" + "=" * 50)
        print(f"🔎 Buscando: {anime}")
        print("=" * 50)

        encontrado = False

        for fuente in fuentes:

            if not fuente["activa"]:
                continue

            nombre_fuente = fuente["nombre"]

            print(
                f"🌐 Probando fuente: {nombre_fuente}"
            )

            try:

                videos = fuente["buscar"](
                    fuente["url"],
                    [anime]
                )

                if videos:

                    print(
                        f"✅ Encontrado en {nombre_fuente}"
                    )

                    resultados.extend(videos)

                    encontrado = True

                    break

                else:

                    print(
                        f"❌ No encontrado en {nombre_fuente}"
                    )

            except Exception as e:

                print(
                    f"⚠️ Error en {nombre_fuente}: {e}"
                )

        if not encontrado:

            print(
                f"❌ No se encontró: {anime}"
            )

    return resultados


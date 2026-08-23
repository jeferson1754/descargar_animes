# animes/buscador.py
import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utilidades.navegador import configurar_navegador
from config import DOWNLOAD_DIR


def extraer_nombres_anime(url, download_dir):
    """
    Extrae únicamente los animes que tienen episodios pendientes 
    detectando la clase 'episode-badge episode-pending'.
    """

    driver = configurar_navegador(download_dir)
    
    if driver is None:
        print("❌ No se pudo iniciar el navegador.")
        return []

    try:
        driver.get(url)

        # 1. Esperar a que la tabla o el cuerpo cargue
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#animeTable tbody"))
            )
        except TimeoutException:
            print("⚠️ No se encontró la tabla de animes o la página demoró en cargar.")
            return []

        # 2. BÚSQUEDA FILTRADA: Selecciona solo filas (tr) que tengan la etiqueta 'episode-pending'
        selector_pendientes = "#animeTable tbody tr:has(.episode-badge.episode-pending)"
        
        filas_pendientes = driver.find_elements(By.CSS_SELECTOR, selector_pendientes)

        # Respaldo: Si el navegador no soporta el pseudoselect :has(), usamos un filtro iterativo
        if not filas_pendientes:
            todas_las_filas = driver.find_elements(By.CSS_SELECTOR, "#animeTable tbody tr")
            filas_pendientes = [
                f for f in todas_las_filas 
                if len(f.find_elements(By.CSS_SELECTOR, ".episode-badge.episode-pending")) > 0
            ]

        animes = []

        for fila in filas_pendientes:
            try:
                # ==========================================
                # NOMBRE DEL ANIME
                # ==========================================
                elemento_nombre = fila.find_element(By.CSS_SELECTOR, "td.fw-500")
                nombre = driver.execute_script(
                    "return arguments[0].childNodes[0].textContent.trim();", 
                    elemento_nombre
                )

                if not nombre:
                    continue

                # ==========================================
                # PROGRESO (Ejemplo: 7/12)
                # ==========================================
                progreso_elemento = fila.find_element(By.CSS_SELECTOR, ".progress-cell span.small")
                texto_progreso = progreso_elemento.text.strip()

                match_progreso = re.search(r"(\d+)\s*/\s*(\d+)", texto_progreso)
                if not match_progreso:
                    continue

                episodio_actual = int(match_progreso.group(1))
                episodios_totales = int(match_progreso.group(2))

                # ==========================================
                # EPISODIOS PENDIENTES
                # ==========================================
                estado_elemento = fila.find_element(By.CSS_SELECTOR, ".episode-badge.episode-pending")
                match_pendientes = re.search(r"(\d+)", estado_elemento.text.strip())
                
                pendientes = int(match_pendientes.group(1)) if match_pendientes else 1

                # El episodio a buscar siempre es el siguiente al actual
                episodio_buscado = episodio_actual + 1

                anime = {
                    "nombre": nombre,
                    "episodio_actual": episodio_actual,
                    "episodios_totales": episodios_totales,
                    "pendientes": pendientes,
                    "episodio_buscado": episodio_buscado
                }

                animes.append(anime)

            except Exception as e:
                print(f"⚠️ Error procesando fila con pendiente: {e}")

        return animes

    finally:
        driver.quit()

def buscar_en_fuentes(animes, fuentes):
    """
    Busca cada anime en las fuentes disponibles.
    Prueba las fuentes en orden hasta encontrar el
    episodio solicitado.
    """

    resultados = []

    driver_capitulos = configurar_navegador(
        DOWNLOAD_DIR
    )

    for anime in animes:

        nombre = anime.get("nombre")
        episodio_buscado = anime.get("episodio_buscado")

        print("\n" + "=" * 60)
        print(f"🔎 Buscando: {nombre}")
        print(
            f"🎯 Episodio: {episodio_buscado}"
        )
        print("=" * 60)

        encontrado = False

        for fuente in fuentes:

            if not fuente.get("activa", True):
                continue

            nombre_fuente = fuente["nombre"]
            url_fuente = fuente["url"]
            funcion_busqueda = fuente["buscar"]

            print(
                f"🌐 Probando fuente: "
                f"{nombre_fuente}"
            )

            try:

                videos = funcion_busqueda(
                    driver_capitulos,
                    url_fuente,
                    [anime]

                )

                if videos:

                    print(
                        f"✅ Encontrado en "
                        f"{nombre_fuente}"
                    )

                    for video in videos:

                        video["fuente"] = (
                            nombre_fuente
                        )

                    resultados.extend(
                        videos
                    )

                    encontrado = True
                    break

                print(
                    f"❌ {nombre_fuente}: "
                    f"episodio no encontrado."
                )

            except Exception as e:

                print(
                    f"⚠️ Error en "
                    f"{nombre_fuente}: {type(e).__name__}: {e}"
                )

        if not encontrado:

            print(
                f"❌ No se encontró "
                f"{nombre} "
                f"episodio {episodio_buscado}"
            )

    driver_capitulos.quit()
    return resultados

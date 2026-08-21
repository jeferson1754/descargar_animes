# animes/buscador.py
import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from fuentes.tioanime import buscar_pagina_principal
from utilidades.navegador import configurar_navegador


def extraer_nombres_anime(url, download_dir):
    """
    Extrae de la tabla:
    - nombre del anime
    - episodio actual
    - total de episodios
    - episodios pendientes
    - episodio que se debe buscar
    """

    driver = configurar_navegador(download_dir)

    try:
        driver.get(url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#animeTable tbody tr")
            )
        )

        filas = driver.find_elements(
            By.CSS_SELECTOR,
            "#animeTable tbody tr"
        )

        animes = []

        for fila in filas:

            try:
                # ==========================================
                # NOMBRE DEL ANIME
                # ==========================================

                elemento_nombre = fila.find_element(
                    By.CSS_SELECTOR,
                    "td.fw-500"
                )

                nombre = driver.execute_script(
                    """
                    return arguments[0]
                        .childNodes[0]
                        .textContent
                        .trim();
                    """,
                    elemento_nombre
                )

                if not nombre:
                    continue

                # ==========================================
                # PROGRESO
                # Ejemplo: 7/12
                # ==========================================

                progreso_elemento = fila.find_element(
                    By.CSS_SELECTOR,
                    ".progress-cell span.small"
                )

                texto_progreso = (
                    progreso_elemento.text.strip()
                )

                match_progreso = re.search(
                    r"(\d+)\s*/\s*(\d+)",
                    texto_progreso
                )

                if not match_progreso:
                    print(
                        f"⚠️ No se pudo obtener "
                        f"el progreso de: {nombre}"
                    )
                    continue

                episodio_actual = int(
                    match_progreso.group(1)
                )

                episodios_totales = int(
                    match_progreso.group(2)
                )

                # ==========================================
                # EPISODIOS PENDIENTES
                # Ejemplo: 1 pendientes
                # ==========================================

                pendientes = 0

                try:
                    estado_elemento = fila.find_element(
                        By.CSS_SELECTOR,
                        "td:nth-child(3) .episode-badge"
                    )

                    texto_estado = (
                        estado_elemento.text.strip()
                    )

                    match_pendientes = re.search(
                        r"(\d+)",
                        texto_estado
                    )

                    if match_pendientes:
                        pendientes = int(
                            match_pendientes.group(1)
                        )

                except Exception:
                    pendientes = 0

                # ==========================================
                # EPISODIO QUE DEBEMOS BUSCAR
                # ==========================================

                if pendientes > 0:
                    episodio_buscado = (
                        episodio_actual + 1
                    )
                else:
                    episodio_buscado = None

                # ==========================================
                # GUARDAR RESULTADO
                # ==========================================

                anime = {
                    "nombre": nombre,
                    "episodio_actual": episodio_actual,
                    "episodios_totales": episodios_totales,
                    "pendientes": pendientes,
                    "episodio_buscado": episodio_buscado
                }

                animes.append(anime)

            except Exception as e:

                print(
                    f"⚠️ Error procesando una fila: {e}"
                )

        return animes

    finally:
        driver.quit()


def buscar_en_fuentes(nombres_animes, fuentes):
    """
    Busca cada anime en las fuentes disponibles.
    Prueba las fuentes en orden hasta encontrar un resultado.
    """

    resultados = []

    for anime in nombres_animes:

        print("\n" + "=" * 60)
        print(f"🔎 Buscando: {anime}")
        print("=" * 60)

        encontrado = False

        for fuente in fuentes:

            if not fuente.get("activa", True):
                continue

            nombre_fuente = fuente["nombre"]
            url_fuente = fuente["url"]
            funcion_busqueda = fuente["buscar"]

            print(
                f"🌐 Probando fuente: {nombre_fuente}"
            )

            try:

                videos = funcion_busqueda(
                    url_fuente,
                    [anime]
                )

                if videos:

                    print(
                        f"✅ Encontrado en {nombre_fuente}"
                    )

                    for video in videos:

                        video["fuente"] = nombre_fuente

                    resultados.extend(videos)

                    encontrado = True
                    break

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

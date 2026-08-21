import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

from utilidades.archivos import leer_nombres_desde_txt, guardar_resultados_videos_txt
from utilidades.navegador import configurar_navegador
from animes.buscador import buscar_en_fuentes
from config import FUENTES_ANIME



def verificar_descarga(
    download_dir,
    archivos_antes,
    tiempo_maximo=900,
    intervalo=2,
    tiempo_estable=6
):
    """
    Espera hasta que aparezca una descarga terminada.

    - Detecta archivos temporales de Chrome (.crdownload)
    - Espera hasta que desaparezcan
    - Comprueba que exista un archivo final
    - Comprueba que su tamaño deje de cambiar
    - Devuelve la ruta del archivo terminado
    """

    inicio = time.time()
    archivo_anterior = None
    tamano_anterior = -1
    segundos_estable = 0

    extensiones_video = (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv"
    )

    extensiones_temporales = (
        ".crdownload",
        ".part",
        ".tmp"
    )

    print("Esperando a que termine la descarga...")

    while time.time() - inicio < tiempo_maximo:

        try:
            archivos_actuales = set(os.listdir(download_dir))
        except OSError as e:
            print(f"❌ No se pudo leer la carpeta de descargas: {e}")
            time.sleep(intervalo)
            continue

        temporales = [
            archivo
            for archivo in archivos_actuales
            if archivo.lower().endswith(
                extensiones_temporales
            )
        ]

        if temporales:
            print(
                f"⬇️ Descarga en progreso... "
                f"({len(temporales)} archivo(s) temporal(es))"
            )

            segundos_estable = 0
            time.sleep(intervalo)
            continue

        # --------------------------------------------------
        # 2. Buscar archivos de video NUEVOS
        # --------------------------------------------------

        archivos_nuevos = (
            archivos_actuales - archivos_antes
        )

        videos_nuevos = [
            archivo
            for archivo in archivos_nuevos
            if archivo.lower().endswith(extensiones_video)
        ]

        if videos_nuevos:

            # El más recientemente modificado
            archivo = max(
                videos_nuevos,
                key=lambda x: os.path.getmtime(
                    os.path.join(download_dir, x)
                )
            )

            ruta = os.path.join(download_dir, archivo)

            try:
                tamano_actual = os.path.getsize(ruta)
            except OSError:
                time.sleep(intervalo)
                continue

            ruta = os.path.join(
                download_dir,
                archivo
            )

            try:

                tamano_actual = os.path.getsize(
                    ruta
                )

            except OSError:

                time.sleep(intervalo)
                continue

            # --------------------------------------------------
            # 3. Comprobar que el archivo deje de crecer
            # --------------------------------------------------

            if archivo == archivo_anterior:

                if tamano_actual == tamano_anterior:
                    segundos_estable += intervalo
                else:
                    segundos_estable = 0

            else:
                archivo_anterior = archivo
                segundos_estable = 0

            tamano_anterior = tamano_actual

            print(
                f"📦 Archivo detectado: {archivo} | "
                f"{tamano_actual / (1024 * 1024):.2f} MB | "
                f"estable: {segundos_estable}s"
            )

            # --------------------------------------------------
            # 4. Confirmación real
            # --------------------------------------------------

            if (
                tamano_actual > 0
                and segundos_estable >= tiempo_estable
            ):
                print(
                    f"✅ Descarga confirmada: {archivo}"
                )

                return ruta

        time.sleep(intervalo)

    # ------------------------------------------------------
    # 5. Timeout
    # ------------------------------------------------------

    minutos = tiempo_maximo // 60

    print(
        f"❌ Timeout: la descarga no terminó "
        f"después de {minutos} minutos."
    )

    return None

def buscar_enlace_descarga_y_actualizar(driver, videos_encontrados):
    """Busca el enlace de descarga (Mega) para cada video y lo agrega a la lista."""

    videos_con_descarga = []

    for video in videos_encontrados:

        # Reutilizamos la lógica de buscar_boton_descarga pero sin hacer clic aún
        enlace_descarga = buscar_boton_descarga(driver, video['enlace'])

        if enlace_descarga:
            video['link_descarga'] = enlace_descarga
        else:
            video['link_descarga'] = "No encontrado"

        videos_con_descarga.append(video)

    return videos_con_descarga

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
    
def detectar_servidor_descarga(driver):
    """
    Detecta el servidor según la URL actual y/o elementos presentes
    en la página.
    """

    url = driver.current_url.lower()

    # -----------------------------------------
    # Servidores conocidos por URL
    # -----------------------------------------

    if "mega.nz" in url:
        return "mega"

    if "mega.co.nz" in url:
        return "mega"

    if "streamtape.com" in url:
        return "streamtape"

    if "voe.sx" in url:
        return "voe"

    if "voe" in url:
        return "voe"

    if "dood" in url:
        return "doodstream"

    # -----------------------------------------
    # Si no se pudo detectar por URL,
    # revisar elementos de la página
    # -----------------------------------------

    try:

        elementos = driver.find_elements(
            By.TAG_NAME,
            "a"
        )

        for elemento in elementos:

            href = elemento.get_attribute("href")

            if not href:
                continue

            href = href.lower()

            if "mega.nz" in href or "mega.co.nz" in href:
                return "mega"

            if "streamtape.com" in href:
                return "streamtape"

            if "voe.sx" in href:
                return "voe"

            if "doodstream" in href:
                return "doodstream"

    except Exception as e:

        print(
            f"⚠️ Error detectando servidor: {e}"
        )

    return "desconocido"

def encontrar_boton_descarga(driver, servidor):
    """
    Busca el botón de descarga dependiendo del servidor.
    """

    selectores = {

        "mega": [
            (
                By.CSS_SELECTOR,
                ".mega-component.lg-size.secondary.icon-loading.visible-txt.nav-elem.normal.button"
            ),
        ],

        "streamtape": [
            (
                By.CSS_SELECTOR,
                "#download"
            ),
        ],

        "voe": [
            (
                By.CSS_SELECTOR,
                "a[href*='download']"
            ),
        ],

        "doodstream": [
            (
                By.CSS_SELECTOR,
                "a[href*='/download/']"
            ),
        ],

    }

    if servidor not in selectores:

        print(
            f"⚠️ Servidor no reconocido: {servidor}"
        )

        return None

    for tipo_selector, selector in selectores[servidor]:

        try:

            boton = WebDriverWait(
                driver,
                10
            ).until(
                EC.element_to_be_clickable(
                    (
                        tipo_selector,
                        selector
                    )
                )
            )

            print(
                f"🖱️ Botón encontrado "
                f"para servidor: {servidor}"
            )

            return boton

        except Exception:

            continue

    print(
        f"❌ No se encontró botón para "
        f"servidor: {servidor}"
    )

    return None


def hacer_click_en_boton_descarga(
    driver,
    enlace_descarga,
    download_dir,
    nombre_video
):
    """
    Inicia una descarga y espera hasta confirmar
    que apareció un archivo nuevo y terminó de crecer.

    Devuelve:
        True  -> descarga confirmada
        False -> descarga fallida
    """

    try:

        # --------------------------------------------------
        # 1. Registrar archivos existentes ANTES
        # --------------------------------------------------

        archivos_antes = set(os.listdir(download_dir))

        print(
            f"\n🌐 Abriendo enlace de descarga para: "
            f"{nombre_video}"
        )

        driver.get(enlace_descarga)

        time.sleep(3)

        # --------------------------------------------------
        # 2. Esperar botón
        # --------------------------------------------------

        # -----------------------------------------
        # Detectar servidor
        # -----------------------------------------

        servidor = detectar_servidor_descarga(
            driver
        )

        print(
            f"🌐 Servidor detectado: {servidor}"
        )

        # -----------------------------------------
        # Buscar botón correspondiente
        # -----------------------------------------

        boton_descarga = encontrar_boton_descarga(
            driver,
            servidor
        )

        if boton_descarga is None:

            print(
                f"❌ No se encontró botón "
                f"de descarga para {nombre_video}"
            )

            return False

        # -----------------------------------------
        # Hacer clic
        # -----------------------------------------

        boton_descarga.click()

        print(
            f"⬇️ Descarga iniciada: {nombre_video}"
        )

        # --------------------------------------------------
        # 4. Esperar confirmación REAL
        # --------------------------------------------------

        archivo_descargado = verificar_descarga(
            download_dir=download_dir,
            archivos_antes=archivos_antes,
            tiempo_maximo=900,
            intervalo=2,
            tiempo_estable=6
        )

        # --------------------------------------------------
        # 5. Resultado
        # --------------------------------------------------

        if archivo_descargado:

            print(
                f"✅ DESCARGA COMPLETADA: "
                f"{nombre_video}"
            )

            print(
                f"📁 Archivo: "
                f"{os.path.basename(archivo_descargado)}"
            )

            return True

        print(
            f"❌ La descarga NO pudo confirmarse: "
            f"{nombre_video}"
        )

        return False

    except Exception as e:

        print(
            f"❌ Error descargando "
            f"{nombre_video}: {e}"
        )

        return False

def descargar_video_con_reintentos(
    video,
    download_dir,
    max_intentos=3
):
    """
    Intenta descargar un video varias veces.
    Crea un driver nuevo en cada intento.
    """

    for intento in range(1, max_intentos + 1):

        print(
            f"\nIntento {intento}/{max_intentos}"
        )

        driver = None

        try:

            driver = configurar_navegador(
                download_dir
            )

            if driver is None:
                raise Exception(
                    "No se pudo iniciar ChromeDriver."
                )

            resultado = hacer_click_en_boton_descarga(
                driver,
                video["link_descarga"],
                download_dir,
                video["nombre"]
            )

            if resultado:

                print(
                    f"✅ Descarga completada: "
                    f"{video['nombre']}"
                )

                return True

            print(
                f"❌ Falló el intento "
                f"{intento}/{max_intentos}"
            )

        except Exception as e:

            print(
                f"❌ Error en intento "
                f"{intento}/{max_intentos}: {e}"
            )

        finally:

            if driver is not None:

                try:
                    driver.quit()
                    print("🔒 Driver cerrado.")

                except Exception as e:

                    print(
                        f"⚠️ Error cerrando driver: {e}"
                    )

        if intento < max_intentos:

            espera = intento * 10

            print(
                f"🔄 Reintentando en "
                f"{espera} segundos..."
            )

            time.sleep(espera)

    return False
    
def flujo_descarga_animes(file_name, download_dir):
    # Leer los videos desde el archivo .txt (solo nombres de animes)
    animes = leer_nombres_desde_txt(
        file_name
    )
    
    nombres_animes = [
        anime["nombre"]
        for anime in animes
    ]

    if not nombres_animes:

        print(
            "❌ No hay animes pendientes para buscar."
        )

        return False

    # Paso 1: Buscar videos relacionados con los animes
    print("Buscando videos relacionados...")
    videos_encontrados = buscar_en_fuentes(
        animes,
        FUENTES_ANIME
    )

    if not videos_encontrados:
        print("No se encontraron videos para los animes indicados.")
        return False

    # Iniciar el navegador para buscar los enlaces de descarga
    driver = configurar_navegador(download_dir)

    # Paso 2: Buscar los enlaces de descarga de Mega y actualizar la lista
    videos_finales = buscar_enlace_descarga_y_actualizar(
        driver, videos_encontrados)

    # Cerra el driver después de obtener los enlaces de Mega
    driver.quit()

    # Paso 3: Guardar resultados de videos encontrados (ahora con el link de descarga)
    guardar_resultados_videos_txt(
        videos_finales, "resultados_videos_con_descarga.txt")

    # Paso 4: Mostrar la información completa antes de preguntar

    # Formatear la lista de animes con los nuevos detalles para la confirmación
    videos_para_mostrar = []
    for video in videos_finales:
        # Crea una cadena legible que incluye el link de descarga
        detalles = (
            f'"nombre": "{video["nombre"]}",\n'
            f'"link_video": "{video["enlace"]}"\n'
            # Agregada '\n' aquí
            f'"link_descarga": "{video["link_descarga"]}"\n'
            + "-" * 40 + "\n"  # Agregado el signo '+'
        )
        videos_para_mostrar.append(detalles)

    if not videos_para_mostrar:
        print("No se encontraron detalles completos de los animes para descargar.")
        return

    # Paso 5: Iniciar descarga automáticamente
    print("\nAnimes encontrados:")
    for idx, video in enumerate(videos_finales, 1):
        print(f"{idx}. {video['nombre']}")

    print("\nIniciando descargas automáticamente...")

    for video in videos_finales:

        if (
            not video["link_descarga"]
            or video["link_descarga"] == "No encontrado"
        ):

            print(
                f"⚠️ Saltando {video['nombre']}: "
                "enlace no disponible."
            )

            continue

        print("\n" + "=" * 60)

        print(
            f"Descargando: "
            f"{video['nombre']}"
        )

        print("=" * 60)

        resultado = descargar_video_con_reintentos(
            video,
            download_dir,
            max_intentos=3
        )

        if not resultado:

            print(
                f"❌ No se pudo descargar: "
                f"{video['nombre']}"
            )
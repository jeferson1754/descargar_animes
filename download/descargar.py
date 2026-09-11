import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import logging
# 📝 Exportar el valor de la variable a un archivo .txt de depuración
import json

from utilidades.archivos import leer_nombres_desde_txt, guardar_resultados_videos_txt
from utilidades.navegador import configurar_navegador
from animes.buscador import buscar_en_fuentes
from config import FUENTES_ANIME, SERVIDOR
from base_excel import obtener_conexion_google_sheets, guardar_y_actualizar_historial_sheets, leer_animes_pendientes, actualizar_estado_google_sheets, guardar_logs_en_sheets
from notificaciones_telegram import enviar_mensaje_telegram

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

    logging.info("Esperando a que termine la descarga...")

    while time.time() - inicio < tiempo_maximo:

        try:
            archivos_actuales = set(os.listdir(download_dir))
        except OSError as e:
            logging.error(f"❌ No se pudo leer la carpeta de descargas: {e}")
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
            logging.info(
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

            logging.info(
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
                logging.info(
                    f"✅ Descarga confirmada: {archivo}"
                )

                return ruta

        time.sleep(intervalo)

    # ------------------------------------------------------
    # 5. Timeout
    # ------------------------------------------------------

    minutos = tiempo_maximo // 60

    logging.error(
        f"❌ Timeout: la descarga no terminó "
        f"después de {minutos} minutos."
    )

    return None


def marcar_anime_descargado_con_selenium(driver, nombre_anime, episodio):
    """
    Navega a la URL del servidor web con Selenium para marcar el anime como descargado.
    """
    try:
        # Construye la URL de actualización con los parámetros necesarios (ajusta según tu PHP)
        url_servidor = f"{SERVIDOR}/Anime/Emision/actualizar.php?nombre_anime={nombre_anime}&episodio={episodio}"
        logging.info(
            f"🌐 Actualizando servidor mediante Selenium: {nombre_anime} - Ep {episodio} / {url_servidor}")

        # El navegador entra a la página de actualización
        driver.get(url_servidor)

        # Opcional: Pequeña pausa para asegurar que el servidor procese la petición en la base de datos
        time.sleep(2)

        logging.info(f"✅ Servidor actualizado exitosamente.")
        
        return True

    except Exception as e:
        logging.error(f"⚠️ Error al actualizar el servidor con Selenium: {e}")
        return False


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

    if driver is None:
        logging.error(
            "❌ No hay driver disponible."
        )
        return None

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
            logging.info(f"No se encontró el botón de descarga en {video_url}")
            return None

    except Exception as e:
        logging.error(f"Error al acceder a {video_url}: {e}")
        return None


def detectar_servidor_descarga(driver):
    """
    Detecta el servidor analizando la URL, los atributos href y 
    el texto visible de los botones o enlaces en páginas intermedias.
    """
    
    # Dar un breve respiro para que carguen los elementos dinámicos de la página intermedia
    time.sleep(2)
    url = driver.current_url.lower()

    # 1. Detección rápida por URL actual
    if "mega.nz" in url or "mega.co.nz" in url:
        return "mega"
    if "streamtape.com" in url:
        return "streamtape"
    if "voe.sx" in url or "voe" in url:
        return "voe"
    if "dood" in url or "doodstream" in url:
        return "doodstream"
    if "mediafire.com" in url:
        return "mediafire"

    # 2. Búsqueda profunda en elementos (Enlaces y Botones)
    try:
        # Buscamos tanto etiquetas 'a' como botones 'button' o divs interactivos
        elementos = driver.find_elements(By.TAG_NAME, "a") + driver.find_elements(By.TAG_NAME, "button")

        for elemento in elementos:
            try:
                href = elemento.get_attribute("href") or ""
                texto_elemento = elemento.text.lower()
                
                contenido_total = (href + " " + texto_elemento).lower()

                if "mega" in contenido_total:
                    return "mega"
                if "streamtape" in contenido_total:
                    return "streamtape"
                if "voe" in contenido_total:
                    return "voe"
                if "dood" in contenido_total:
                    return "doodstream"
                if "mediafire" in contenido_total:
                    return "mediafire"
            except Exception:
                continue

    except Exception as e:
        logging.error(f"⚠️ Error detectando servidor en página intermedia: {e}")

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
        "mediafire": [
            (By.CSS_SELECTOR, "#downloadButton"),
            (By.CSS_SELECTOR, "a.popservers"),
            (By.CSS_SELECTOR, "a[aria-label*='Download file']")
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

        logging.error(
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

            logging.info(
                f"🖱️ Botón encontrado "
                f"para servidor: {servidor}"
            )

            return boton

        except Exception:

            continue

    logging.error(
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

        logging.info(
            f"\n🌐 Abriendo enlace de descarga para: "
            f"{nombre_video}"
        )

        driver.get(enlace_descarga)

        time.sleep(3)

        # --------------------------------------------------
        # 2. Detectar servidor
        # --------------------------------------------------

        servidor = detectar_servidor_descarga(
            driver
        )

        logging.info(
            f"🌐 Servidor detectado: {servidor}"
        )

        # --------------------------------------------------
        # 3. Validación específica para MEGA (Errores comunes)
        # --------------------------------------------------

        if servidor == "mega":
            logging.info("🔍 Verificando estado del archivo en Mega...")
            try:
                # Damos un par de segundos por si Mega tarda en renderizar el aviso en pantalla
                time.sleep(2)

                texto_pagina = driver.page_source.lower()

                # Verificamos si aparece el mensaje exacto o variaciones comunes
                if "el archivo ya no está disponible" in texto_pagina or "file no longer available" in texto_pagina or "acceder al archivo" in texto_pagina:
                    logging.error(f"❌ Error en Mega: El archivo ya no está disponible.")
                    return "archivo_caido"

                if "archivo no encontrado" in texto_pagina or "file not found" in texto_pagina:
                    logging.error(
                        f"❌ Error en Mega: El archivo no fue encontrado o fue eliminado.")
                    return "archivo_caido"

                '''
                if texto_pagina or "bandwidth quota exceeded" in texto_pagina or "quota exceeded" in texto_pagina:
                    logging.info(f"⚠️ Error en Mega: Se ha agotado la cuota de transferencia.")
                    return "archivo_caido"
                '''

            except Exception as e:
                logging.error(f"⚠️ No se pudo verificar el estado de Mega: {e}")

        # --------------------------------------------------
        # 4. Buscar botón correspondiente
        # --------------------------------------------------

        boton_descarga = encontrar_boton_descarga(
            driver,
            servidor
        )

        if boton_descarga is None:

            logging.error(
                f"❌ No se encontró botón "
                f"de descarga para {nombre_video}"
            )

            return False

        # -----------------------------------------
        # Hacer clic
        # -----------------------------------------

        boton_descarga.click()

        logging.info(
            f"⬇️ Descarga iniciada: {nombre_video}"
        )

        # --------------------------------------------------
        # 5. Esperar confirmación REAL
        # --------------------------------------------------

        archivo_descargado = verificar_descarga(
            download_dir=download_dir,
            archivos_antes=archivos_antes,
            tiempo_maximo=900,
            intervalo=2,
            tiempo_estable=6
        )

        # --------------------------------------------------
        # 6. Resultado
        # --------------------------------------------------

        if archivo_descargado:

            logging.info(
                f"✅ DESCARGA COMPLETADA: "
                f"{nombre_video}"
            )

            logging.info(
                f"📁 Archivo: "
                f"{os.path.basename(archivo_descargado)}"
            )

            return True

        logging.error(
            f"❌ La descarga NO pudo confirmarse: "
            f"{nombre_video}"
        )

        return False

    except Exception as e:

        logging.error(
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

        logging.info(
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

            # Si la descarga fue exitosa
            if resultado is True:
                logging.info(
                    f"✅ Descarga completada: "
                    f"{video['nombre']}"
                )
                return True

            # Si detectó un error crítico de cuota o archivo caí­do, detiene los reintentos inmediatamente y lo propaga
            if resultado in ["archivo_caido", "cuota_agotada"]:
                return resultado

            logging.error(
                f"❌ Falló el intento "
                f"{intento}/{max_intentos}"
            )

        except Exception as e:

            logging.error(
                f"❌ Error en intento "
                f"{intento}/{max_intentos}: {e}"
            )

        finally:

            if driver is not None:

                try:
                    driver.quit()
                    logging.info("🔒 Driver cerrado.")

                except Exception as e:

                    logging.error(
                        f"⚠️ Error cerrando driver: {e}"
                    )

        if intento < max_intentos:

            espera = intento * 10

            logging.info(
                f"🔄 Reintentando en "
                f"{espera} segundos..."
            )

            time.sleep(espera)

    return False

# ==========================================
# MÓDULO 1: BÚSQUEDA, VALIDACIÓN Y SHEETS (NUBE)
# ==========================================


def validar_enlace_mega(driver, enlace):
    """
    Entra al enlace de Mega y comprueba si el archivo está disponible
    y con cuota de transferencia activa.
    Devuelve True si es válido, False si está caído.
    """
    if not enlace or "mega.nz" not in enlace.lower():
        return True  # Si no es de Mega, lo damos por bueno por defecto

    try:
        driver.get(enlace)
        time.sleep(5)
        texto_pagina = driver.page_source.lower()

        # Si encuentra errores típicos de Mega, retorna False
        if any(error in texto_pagina for error in [
            "el archivo ya no está disponible",
            "file no longer available",
            "archivo no encontrado",
            "file not found",
            "bandwidth quota exceeded"
        ]):
            return False

        return True  # Todo OK

    except Exception:
        return False  # Si hubo un error de red o carga, consideramos que falló


def flujo_descarga_animes(file_name, download_dir):

    # Leer los datos desde el archivo .json / .txt
    datos_crudos = leer_nombres_desde_txt(file_name)

    if not datos_crudos:
        logging.error("❌ No hay animes pendientes para buscar.")
        return False
# 2. Expandir los animes según sus episodios pendientes PRIMERO
    animes_a_expandir = []

    for item in datos_crudos:
        nombre = item.get("nombre")
        episodio_actual = item.get("episodio_actual", 0)
        pendientes = item.get("pendientes", 0)

        if pendientes > 0:
            for i in range(1, pendientes + 1):
                ep_buscado = episodio_actual + i
                animes_a_expandir.append({
                    "nombre": nombre,
                    "episodio_buscado": ep_buscado
                })
        else:
            animes_a_expandir.append(item)

    if not animes_a_expandir:
        logging.error("❌ No hay episodios pendientes para procesar.")
        return False

    # ==================================================================
    # ☁️ FILTRO INTELIGENTE DE GOOGLE SHEETS (Nombre + Episodio)
    # ==================================================================
    logging.info("☁️ Conectando con Google Sheets para verificar el historial previo...")
    sheet_service = obtener_conexion_google_sheets()
    animes_en_sheet = leer_animes_pendientes(
        sheet_service) if sheet_service else []

    animes_a_buscar = []
    for anime_obj in animes_a_expandir:
        nombre_obj = anime_obj.get("nombre", "").lower()
        ep_obj = str(anime_obj.get("episodio_buscado", ""))

        # Verificamos si ESTE EXACTO anime Y episodio ya están en la hoja
        ya_registrado = any(
            a["nombre"].lower() == nombre_obj and str(a["episodio"]) == ep_obj
            for a in animes_en_sheet
        )

        if ya_registrado:
            logging.info(
                f"⏩ Omitiendo '{anime_obj.get('nombre')}' (Ep. {ep_obj}): ya se encuentra registrado en Google Sheets.")
        else:
            animes_a_buscar.append(anime_obj)

    if not animes_a_buscar:
        logging.error("❌ No hay episodios nuevos para buscar después de revisar Google Sheets.")
        return False
    # ==================================================================

    # Paso 1: Buscar videos relacionados únicamente con los que pasaron el filtro
    logging.info("Buscando videos relacionados...")
    videos_encontrados = buscar_en_fuentes(
        animes_a_buscar,
        FUENTES_ANIME
    )

    with open("videos_encontrados.txt", "w", encoding="utf-8") as archivo_txt:
        json.dump(videos_encontrados, archivo_txt, ensure_ascii=False, indent=4)

    # ==================================================================
    # 📲 NOTIFICACIÓN SI NO SE ENCONTRARON VIDEOS
    # ==================================================================
    if not videos_encontrados:
        mensaje_telegram = (
            "⚠️ <b>No se encontraron episodios en la búsqueda</b>\n\n"
        )
        mensaje_telegram += "<b>Episodios consultados sin resultados:</b>\n"

        for item in animes_a_buscar:
            nombre = item.get("nombre")
            ep = item.get("episodio_buscado", item.get("episodio_actual", "?"))
            mensaje_telegram += f"• <b>{nombre}</b> — Ep. {ep}\n"

        logging.info("No se encontraron videos para los animes indicados.")

        # Envío a Telegram
        enviar_mensaje_telegram(mensaje_telegram)

        return False

    proceso_nube_buscar_y_guardar_sheets(download_dir, videos_encontrados)

    



def proceso_nube_buscar_y_guardar_sheets(download_dir, videos_encontrados):
    """
    Busca los enlaces de descarga, valida si Mega está activo/con cuota,
    los guarda en Google Sheets y genera el respaldo local.
    """
    driver = configurar_navegador(download_dir)

    if driver is None:
        logging.error("❌ No se pudo iniciar el navegador para obtener los enlaces de descarga.")
        return False

    try:
# 🛡️ Validar si la fuente es TioAnime
        # Verificamos si algún elemento no pertenece a TioAnime (ej. JKAnime)
        es_tioanime = all(
            str(video.get("fuente", "")).lower() == "tioanime" 
            for video in videos_encontrados
        )

        if es_tioanime:
            # Si es TioAnime, procedemos con su lógica de búsqueda de enlaces habitual
            videos_brutos = buscar_enlace_descarga_y_actualizar(
                driver,
                videos_encontrados
            )
        else:
            # Si la fuente es otra (ej. JKAnime), los enlaces ya vienen listos en 'link_descarga'
            logging.info("ℹ️ Fuente detectada distinta de TioAnime. Usando 'link_descarga' preexistente.")
            videos_brutos = videos_encontrados
        
        with open("videos_brutos.txt", "w", encoding="utf-8") as archivo_txt:
            json.dump(videos_brutos, archivo_txt, ensure_ascii=False, indent=4)

        if not videos_brutos:
            logging.error("❌ No se obtuvieron enlaces de descarga para validar.")
            return False

        # 🛡️ Validación de estado en Mega para cada video encontrado
        logging.info("\n🔎 Validando estado de los enlaces en Mega...")
        videos_finales = []  # <--- Creamos una lista nueva vacía para los resultados limpios

        for video in videos_brutos:
            enlace_mega = video.get("link_descarga") or video.get("enlace")

            # 1. Evaluamos la validación
            es_valido = validar_enlace_mega(driver, enlace_mega)

            if es_valido:
                # Si es True: Lo marcamos como Pendiente y lo guardamos en la lista temporal
                logging.info(f"✅ Enlace válido para: {video.get('nombre')}")
                video["estado"] = "Pendiente"
                videos_finales.append(video)
            else:
                # Si es False: El enlace falló
                logging.error(
                    f"❌ Enlace caído o con cuota en Mega para {video.get('nombre')}. Buscando en otra fuente...")
    

    finally:
        try:
            driver.quit()
            logging.info("🔒 Driver de búsqueda cerrado.")
        except Exception as e:
            logging.error(f"⚠️ No se pudo cerrar el driver: {e}")

    if not videos_finales:
        logging.error("❌ No se encontraron videos finales válidos para guardar.")
        return False

    # ☁️ Sincronización con Google Sheets
    logging.info("\n☁️ Conectando con Google Sheets para guardar enlaces...")
    sheet_service = obtener_conexion_google_sheets()

    if sheet_service:
        guardar_y_actualizar_historial_sheets(sheet_service, videos_finales)
    else:
        logging.error("⚠️ No se pudo guardar en Google Sheets, respaldo local disponible.")

    # Respaldo en TXT
    guardar_resultados_videos_txt(
        videos_finales, "resultados_videos_con_descarga.txt")
    logging.info("🎉 Proceso en la nube finalizado con éxito.")

    return videos_finales

# ==========================================
# MÓDULO 2: DESCARGA LOCAL Y ACTUALIZACIÓN
# ==========================================


def proceso_local_descargar_archivos(download_dir):
    """
    Se conecta a Google Sheets, lee los animes pendientes, y ejecuta 
    la descarga local de cada uno, actualizando el servidor al terminar.
    """
    logging.info("\n☁️ Conectando con Google Sheets para leer animes pendientes...")
    sheet_service = obtener_conexion_google_sheets()
    
    if not sheet_service:
        logging.error("❌ No se pudo conectar con Google Sheets.")
        return

    # 1. Leemos los registros desde tu Google Sheets usando la función que creamos antes
    registros_hoja = leer_animes_pendientes(sheet_service)
    
    if not registros_hoja:
        logging.info("ℹ️ No hay registros en Google Sheets.")
        return

  # 2. Filtramos los que tengan estado "Pendiente" o "Cambiar Fuente"
    videos_finales = [
        {
            "nombre": r.get("nombre"),
            "fuente": r.get("fuente"),
            "nombre_anime": r.get("nombre"), # Compatibilidad por si tu lógica usa esta llave
            "episodio_buscado": r.get("episodio"),
            "episodio": r.get("episodio"),
            "link_descarga": r.get("enlace"),
            "estado": r.get("estado")
        }
        for r in registros_hoja 
        if r.get("estado", "").lower() in ["pendiente", "cambiar fuente"]
    ]

    if not videos_finales:
        logging.info("🎉 ¡No hay animes pendientes o para cambiar fuente en Google Sheets!")
        return

    logging.info(f"\nAnimes listos para descargar ({len(videos_finales)}):")
    for idx, video in enumerate(videos_finales, 1):
        logging.info(f"{idx}. {video.get('nombre')} - Ep: {video.get('episodio_buscado')} [{video.get('estado', 'Desconocido')}]")

    logging.info("\nIniciando descargas automáticamente...")

    driver_servidor = configurar_navegador(download_dir)
    if driver_servidor is None:
        logging.error("❌ No se pudo iniciar el navegador para las descargas.")
        return

    try:
        for video in videos_finales:
            link_descarga = video.get("link_descarga")
            
            # Si el enlace no existe, está caído o la cuota de Mega está agotada, lo saltamos
            if not link_descarga or link_descarga == "No encontrado" or video.get("estado") in ["Archivo Caído", "Cuota Agotada"]:
                logging.info(f"⚠️ Saltando {video.get('nombre')}: enlace no disponible o bloqueado por Mega.")
                # Cuando detectes que un archivo no está disponible o da error de cuota:
                mensaje = f"⚠️ *Alerta de Enlace*\n\n🎬 Anime: *{video.get('nombre')}*\n🔴 Estado: Archivo Caído o Cuota Agotada."
                enviar_mensaje_telegram(mensaje)
                continue

            logging.info("\n" + "=" * 60)
            logging.info(f"Descargando: {video.get('nombre')} - Episodio {video.get('episodio_buscado')}")
            logging.info("=" * 60)
            
            
            resultado = descargar_video_con_reintentos(
                video,
                download_dir,
                max_intentos=3
            )
            
            with open("resultados.txt", "w", encoding="utf-8") as archivo_txt:
                json.dump(resultado, archivo_txt, ensure_ascii=False, indent=4)

                        # 1. Actualizar el servidor local (tu lógica actual)
            nombre_servidor = video.get('nombre_anime') or video.get('nombre')
            episodio_servidor = video.get('episodio_buscado') or video.get('episodio')
            
            # Dentro del ciclo de descargas de tu función:
            # 2. Manejo de resultados post-intento de descarga
            # Dentro del ciclo de descargas de tu función:
            if resultado in ["archivo_caido", "cuota_agotada"]:
                estado_error = "Archivo Caído" if resultado == "archivo_caido" else "Cuota Agotada"
                logging.error(f"❌ {estado_error} detectado en {nombre_servidor}. Buscando otra fuente inmediatamente...")

                enviar_mensaje_telegram(
                    f"🔄 *Cambiando de Fuente*\n\n🎬 Anime: *{nombre_servidor}*\n📺 Episodio: *{episodio_servidor}*\n🔴 Motivo: *{estado_error}*"
                )

                # 1. Acumular fuentes fallidas (Historial previo + Fuente actual)
                fuente_actual = video.get("fuente", "Desconocida")
                fallidas_previas_str = video.get("fuentes_fallidas", "")
                
                lista_excluidas = [f.strip() for f in fallidas_previas_str.split(",") if f.strip()]
                if fuente_actual and fuente_actual not in lista_excluidas:
                    lista_excluidas.append(fuente_actual)
                    
                nueva_cadena_fallidas = ", ".join(lista_excluidas) # Resultado ej: "TioAnime, JKAnime"

                episodio_limpio = int(episodio_servidor) if str(episodio_servidor).isdigit() else episodio_servidor
                link_anterior = video.get("link_descarga")

                logging.info(f"🚫 Fuentes descartadas acumuladas: {nueva_cadena_fallidas}")

                # 2. Re-buscar excluyendo TODAS las fuentes fallidas
                nuevo_video_encontrado = buscar_en_fuentes(
                    [{"nombre": nombre_servidor, "episodio_buscado": episodio_limpio}],
                    FUENTES_ANIME,
                    excluir_fuente=lista_excluidas  # Pasa la lista completa
                )

                videos_finales = []
                if nuevo_video_encontrado:
                    try:
                        es_tioanime = all(
                            str(v.get("fuente", "")).lower() == "tioanime" 
                            for v in nuevo_video_encontrado
                        )

                        if es_tioanime:
                            videos_brutos = buscar_enlace_descarga_y_actualizar(
                                driver_servidor,
                                nuevo_video_encontrado
                            )
                        else:
                            logging.info("ℹ️ Fuente distinta de TioAnime. Usando 'link_descarga' preexistente.")
                            videos_brutos = nuevo_video_encontrado

                        # Validar los nuevos enlaces obtenidos en Mega
                        for v in videos_brutos:
                            enlace_mega = v.get("link_descarga") or v.get("enlace")
                            if validar_enlace_mega(driver_servidor, enlace_mega):
                                logging.info(f"✅ Enlace válido en Mega para: {v.get('nombre')}")
                                v["estado"] = "Pendiente"
                                videos_finales.append(v)
                            else:
                                logging.error("❌ El enlace de la nueva fuente también está caído en Mega.")

                    except Exception as e:
                        logging.error(f"⚠️ Error procesando la re-búsqueda de fuente: {e}")

                # 3. Evaluar resultado y actualizar tanto objeto local como Google Sheets
                if videos_finales and videos_finales[0].get("link_descarga") != link_anterior:
                    nueva_fuente_nombre = videos_finales[0].get("fuente", "Desconocida")
                    nuevo_link_descarga = videos_finales[0].get("link_descarga")

                    # A) Actualizar diccionario local en memoria
                    video["link_descarga"] = nuevo_link_descarga
                    video["fuente"] = nueva_fuente_nombre
                    video["fuentes_fallidas"] = nueva_cadena_fallidas

                    logging.info(f"✅ Nueva fuente '{nueva_fuente_nombre}' encontrada. Sincronizando Sheets...")

                    # B) Sincronizar en Google Sheets
                    actualizar_estado_google_sheets(
                        sheet_service=sheet_service,
                        nombre_hoja="Animes",
                        nombre_anime=nombre_servidor,
                        episodio=episodio_limpio,
                        nuevo_enlace=nuevo_link_descarga,
                        nueva_fuente=nueva_fuente_nombre,
                        fuentes_fallidas=nueva_cadena_fallidas,
                        nuevo_estado="Pendiente"
                    )
                    continue  # Vuelve a intentar la descarga con el nuevo enlace
                else:
                    logging.error("❌ No se encontraron fuentes alternativas válidas. Guardando 'Sin Fuentes'.")
                    video["fuentes_fallidas"] = nueva_cadena_fallidas

                    actualizar_estado_google_sheets(
                        sheet_service=sheet_service,
                        nombre_hoja="Animes",
                        nombre_anime=nombre_servidor,
                        episodio=episodio_limpio,
                        fuentes_fallidas=nueva_cadena_fallidas,
                        nuevo_estado="Sin Fuentes"
                    )
                    
                    # Cuando se agotan las opciones y pasa a 'Sin Fuentes'
                    mensaje_sin_fuentes = (
                        f"⚠️ *Alerta: Episodio Sin Fuentes*\n\n"
                        f"🎬 Anime: *{nombre_servidor}*\n"
                        f"📺 Episodio: *{episodio_limpio}*\n"
                        f"🔴 Estado: *Sin Fuentes Disponibles*\n"
                        f"📝 Nota: Se probaron todas las fuentes descartadas ({nueva_cadena_fallidas}) sin enlace válido en Mega."
                    )
                    enviar_mensaje_telegram(mensaje_sin_fuentes)
                    continue
        
            
            # Dentro del bloque 'else' cuando tu script local completa la descarga y actualiza a Completado:
            mensaje = f"📥 *Descarga Exitosa*\n\n🎬 Anime: *{nombre_servidor}*\n📺 Episodio: *{episodio_servidor}*\n🟢 Estado: Completado y Servidor Local actualizado."
            enviar_mensaje_telegram(mensaje)
            
            if nombre_servidor and episodio_servidor:
                marcar_anime_descargado_con_selenium(
                    driver_servidor, 
                    nombre_servidor, 
                    episodio_servidor
                )
                
                actualizar_estado_google_sheets(
                    sheet_service=sheet_service,
                    nombre_hoja="Animes",                      # El nombre de la pestaña de tu hoja
                    nombre_anime=nombre_servidor,
                    episodio=episodio_servidor,
                    nuevo_estado="Completado"
                )
            else:
                logging.error("⚠️ No se pudieron obtener los datos exactos para actualizar el servidor.")

    finally:
        try:
            driver_servidor.quit()
            logging.info("🔒 Driver de servidor cerrado.")
        except:
            pass
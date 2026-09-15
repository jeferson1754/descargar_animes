import os
import logging
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2, SERVIDOR
from animes.buscador import extraer_nombres_anime
from utilidades.archivos import (
    guardar_archivos_descargados,
    guardar_animes_no_descargados,
    leer_nombres_animes_a_descargar,
    mover_videos_y_limpiar_carpetas,
    eliminar_txt,
    guardar_resultados_animes_json
)
from animes.comparador import obtener_archivos_descargados
from download.descargar import flujo_descarga_animes
from base_excel import (
    obtener_conexion_google_sheets,
    leer_animes_pendientes,
    verificar_animes_desaparecidos,
    guardar_logs_en_sheets
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def procesar_animes(download_dir, archivo_animes, archivo_resultado_descargados, archivo_resultado_no_descargados):
    mover_videos_y_limpiar_carpetas(download_dir, download_dir)

    animes_a_descargar = leer_nombres_animes_a_descargar(archivo_animes)

    if not animes_a_descargar:
        logging.info(
            "✅ No hay animes pendientes por descargar según la base de datos.")
        guardar_animes_no_descargados([], archivo_resultado_no_descargados)
        return False

    logging.info(
        f"\n📺 Animes pendientes por procesar ({len(animes_a_descargar)}):")
    for anime in animes_a_descargar:
        logging.info(f"   • {anime}")

    guardar_animes_no_descargados(
        animes_a_descargar, archivo_resultado_no_descargados)

    archivos_locales = obtener_archivos_descargados(download_dir)
    if archivos_locales:
        guardar_archivos_descargados(
            archivos_locales, archivo_resultado_descargados)

    return bool(animes_a_descargar)


def ejecutar_opcion_2():
    download_dir = DOWNLOAD_DIR if os.path.exists(
        DOWNLOAD_DIR) else DOWNLOAD_DIR_2
    print(f"📁 Usando directorio: {download_dir}")

    url = f"{SERVIDOR}Anime/Emision/descargar.php?faltantes=&accion=HOY"
    logging.info(
        "--- AUTOMÁTICO: BÚSQUEDA DE ANIMES PENDIENTES/FALTANTES (OPCIÓN 2) ---")

    nombres_anime = extraer_nombres_anime(url, download_dir)

    if not nombres_anime:
        logging.error("❌ No se encontraron animes para procesar.")
        eliminar_txt()
        return

    sheet_service = obtener_conexion_google_sheets()
    if sheet_service:
        animes_previos_sheets = leer_animes_pendientes(sheet_service)
        verificar_animes_desaparecidos(
            sheet_service, animes_previos_sheets, nombres_anime)

    archivo_animes = "resultados_anime.txt"
    archivo_resultado_descargados = "archivos_descargados.txt"
    archivo_resultado_no_descargados = "animes_no_descargados.txt"

    guardar_resultados_animes_json(nombres_anime, archivo_animes)

    logging.info(f"Cantidad de animes extraídos: {len(nombres_anime)}")
    for nombre in nombres_anime:
        logging.info(nombre)
    logging.info(f"Datos guardados en '{archivo_animes}'")

    procesar_animes(
        download_dir,
        archivo_animes,
        archivo_resultado_descargados,
        archivo_resultado_no_descargados
    )

    if not os.path.exists(archivo_resultado_no_descargados) or os.path.getsize(archivo_resultado_no_descargados) == 0:
        logging.info("No hay nuevos animes pendientes para buscar videos.")
    else:
        flujo_descarga_animes(archivo_resultado_no_descargados, download_dir)
        if sheet_service:
            guardar_logs_en_sheets(sheet_service)

    eliminar_txt()
    logging.info("✅ Proceso finalizado.")


if __name__ == "__main__":
    ejecutar_opcion_2()

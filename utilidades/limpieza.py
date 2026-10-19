import logging
import os
import time


def ejecutar_rutina_limpieza(
    directorio_capturas="debug_screenshots",
    dias_retencion_capturas=5,
    archivos_temporales=None,
):
    """Elimina capturas de pantalla antiguas y purga archivos temporales

    residuales del ciclo de ejecución.
    """
    logging.info("🧹 Iniciando rutina de auto-limpieza del sistema...")

    # ============================================================
    # 1. LIMPIEZA DE CAPTURAS DE PANTALLA (POR ANTIGÜEDAD)
    # ============================================================
    if os.path.exists(directorio_capturas):
        ahora = time.time()
        limite_segundos = dias_retencion_capturas * 86400
        capturas_eliminadas = 0

        for archivo in os.listdir(directorio_capturas):
            ruta_archivo = os.path.join(directorio_capturas, archivo)

            if os.path.isfile(ruta_archivo):
                # Verificar tiempo de modificación del archivo
                mtime = os.path.getmtime(ruta_archivo)
                if (ahora - mtime) > limite_segundos:
                    try:
                        os.remove(ruta_archivo)
                        capturas_eliminadas += 1
                    except Exception as e:
                        logging.warning(
                            f"⚠️ No se pudo eliminar la captura {archivo}: {e}"
                        )

        if capturas_eliminadas > 0:
            logging.info(
                f"📸 Se eliminaron {capturas_eliminadas} capturas con más de {dias_retencion_capturas} días en '{directorio_capturas}'."
            )
        else:
            logging.info("📸 No hay capturas antiguas pendientes de eliminar.")
    else:
        logging.info(
            f"ℹ️ La carpeta '{directorio_capturas}' no existe. Omite paso."
        )

    # ============================================================
    # 2. LIMPIEZA / REINICIO DE ARCHIVOS TXT/JSON TEMPORALES
    # ============================================================
    if archivos_temporales is None:
        archivos_temporales = [
            "videos_tioanime.txt",
            "videos_encontrados.txt",
            "resultados_anime.txt",
            "resultados.txt"
        ]

    temporales_removidos = 0
    for temp_file in archivos_temporales:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                temporales_removidos += 1
            except Exception as e:
                logging.warning(
                    f"⚠️ No se pudo eliminar el archivo temporal {temp_file}: {e}"
                )

    if temporales_removidos > 0:
        logging.info(
            f"📄 Se purgaron {temporales_removidos} archivos temporales de ciclo."
        )

    logging.info("✅ Rutina de auto-limpieza finalizada exitosamente.")
    
def limpiar_videos_descargados(
    directorio_descargas,
    dias_retencion=7,
    extensiones=(".mp4", ".mkv", ".avi"),
):
    """Elimina archivos de video en 'directorio_descargas' que superen

    los 'dias_retencion' de antigüedad.
    """
    if not os.path.exists(directorio_descargas):
        logging.warning(
            f"⚠️ El directorio de descargas no existe: {directorio_descargas}"
        )
        return

    logging.info(
        f"🎬 Verificando videos para eliminar en: {directorio_descargas}"
    )

    ahora = time.time()
    limite_segundos = dias_retencion * 86400
    videos_eliminados = 0
    espacio_liberado_bytes = 0

    for raiz, _, archivos in os.walk(directorio_descargas):
        for archivo in archivos:
            if archivo.lower().endswith(extensiones):
                ruta_archivo = os.path.join(raiz, archivo)

                try:
                    mtime = os.path.getmtime(ruta_archivo)
                    if (ahora - mtime) > limite_segundos:
                        tamano = os.path.getsize(ruta_archivo)
                        os.remove(ruta_archivo)

                        videos_eliminados += 1
                        espacio_liberado_bytes += tamano
                        logging.info(f"🗑️ Video eliminado por antigüedad: {archivo}")

                except Exception as e:
                    logging.warning(
                        f"⚠️ No se pudo eliminar el video {archivo}: {e}"
                    )

    if videos_eliminados > 0:
        espacio_mb = espacio_liberado_bytes / (1024 * 1024)
        logging.info(
            f"🧹 Limpieza de videos finalizada: {videos_eliminados} archivo(s) eliminado(s) "
            f"({espacio_mb:.2f} MB liberados)."
        )
    else:
        logging.info("🎬 No hay videos antiguos pendientes de eliminación.")
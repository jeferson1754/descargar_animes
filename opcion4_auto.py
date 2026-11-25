import os
import logging
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2, URL_ANIMES_VISTOS
from animes.buscador import extraer_nombres_anime
from download.descargar import proceso_local_descargar_archivos
from utilidades.limpieza import (
    ejecutar_rutina_limpieza,
    limpiar_videos_vistos,
    limpiar_carpetas_fechas_vacias,
)
from base_excel import (
    obtener_conexion_google_sheets,
    leer_animes_pendientes,
    verificar_animes_desaparecidos,
    guardar_logs_en_sheets,
)
from recorte.api_anime import ejecucion_recortador
from notificaciones_telegram import enviar_mensaje_telegram

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def _sincronizar_y_limpiar_vistos(download_dir, sheet_service):
    """Marca como 'Visto' en Sheets lo que ya no está en la web y borra sus videos."""
    if not sheet_service:
        logging.warning("⚠️ Sin conexión a Google Sheets: se omite limpieza de vistos.")
        return

    registros_sheets = leer_animes_pendientes(sheet_service)
    animes_web = extraer_nombres_anime(
        URL_ANIMES_VISTOS, download_dir, retornar_none_si_error=True
    )

    if animes_web is not None:
        actualizados = verificar_animes_desaparecidos(
            sheet_service,
            registros_sheets,
            animes_web,
            estados_objetivo=("pendiente", "completado", "descargado"),
        )
        if actualizados > 0:
            registros_sheets = leer_animes_pendientes(sheet_service)

    limpiar_videos_vistos(download_dir, registros_sheets, sheet_service=sheet_service)


def ejecutar_opcion_4():
    download_dir = DOWNLOAD_DIR if os.path.exists(
        DOWNLOAD_DIR) else DOWNLOAD_DIR_2
    sheet_service = None
    se_descargaron_archivos = False

    try:
        print(f"📁 Usando directorio: {download_dir}")

        # Obtener conexión con Google Sheets para el registro de logs y vistos
        sheet_service = obtener_conexion_google_sheets()

        logging.info(
            "\n--- AUTOMÁTICO: INICIANDO DESCARGA LOCAL DESDE GOOGLE SHEETS (OPCIÓN 4) ---")

        # Ejecutar proceso de descarga local
        se_descargaron_archivos = proceso_local_descargar_archivos(
            download_dir
        )

        logging.info("✅ Proceso de descarga local finalizado.")
    except Exception as e:
        logging.error(f"❌ Error crítico en ciclo automático: {e}")
        enviar_mensaje_telegram(
            f"⚠️ <b>Alerta de Error:</b> Ocurrió un fallo en el ciclo automático:\n<code>{e}</code>"
        )

    finally:
        # Ejecutar auto-limpieza al terminar el flujo (éxito o fallo)
        ejecutar_rutina_limpieza(
            directorio_capturas="debug_screenshots",
            dias_retencion_capturas=3,  # Mantiene capturas de los últimos 3 días
        )

        _sincronizar_y_limpiar_vistos(download_dir, sheet_service)
        limpiar_carpetas_fechas_vacias(download_dir)

        ejecucion_recortador()

        if sheet_service:
            guardar_logs_en_sheets(sheet_service)

        # Un único mensaje de cierre según el resultado
        if se_descargaron_archivos:
            mensaje_final = (
                "🏁 <b>Proceso Finalizado</b>\n\n"
                "✅ Se completó la descarga de los episodios pendientes."
            )
        else:
            mensaje_final = (
                "🏁 <b>Proceso Finalizado</b>\n\n"
                "🎉 <b>¡Todo al día!</b> No había animes pendientes por descargar."
            )

        enviar_mensaje_telegram(mensaje_final)


if __name__ == "__main__":
    ejecutar_opcion_4()

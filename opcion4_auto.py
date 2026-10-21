import os
import logging
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2
from download.descargar import proceso_local_descargar_archivos
from utilidades.limpieza import ejecutar_rutina_limpieza, limpiar_videos_descargados, limpiar_carpetas_fechas_vacias
from base_excel import (
    obtener_conexion_google_sheets,
    guardar_logs_en_sheets
)
from notificaciones_telegram import enviar_mensaje_telegram

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def ejecutar_opcion_4():
    try:
        download_dir = DOWNLOAD_DIR if os.path.exists(
            DOWNLOAD_DIR) else DOWNLOAD_DIR_2
        print(f"📁 Usando directorio: {download_dir}")

        # Obtener conexión con Google Sheets para el registro de logs
        sheet_service = obtener_conexion_google_sheets()

        logging.info(
            "\n--- AUTOMÁTICO: INICIANDO DESCARGA LOCAL DESDE GOOGLE SHEETS (OPCIÓN 4) ---")

        # Ejecutar proceso de descarga local
        se_descargaron_archivos = proceso_local_descargar_archivos(
            download_dir
        )

        # Guardar historial de logs en Google Sheets si la conexión existe
        if sheet_service:
            guardar_logs_en_sheets(sheet_service)

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

        limpiar_videos_descargados(
            directorio_descargas=download_dir,
            dias_retencion=7,
        )
        
        limpiar_carpetas_fechas_vacias(download_dir)

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

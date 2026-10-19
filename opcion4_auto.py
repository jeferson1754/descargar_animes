import os
import logging
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2
from download.descargar import proceso_local_descargar_archivos
from utilidades.limpieza import ejecutar_rutina_limpieza, limpiar_videos_descargados
from base_excel import (
    obtener_conexion_google_sheets,
    guardar_logs_en_sheets
)

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
        proceso_local_descargar_archivos(download_dir)

        # Guardar historial de logs en Google Sheets si la conexión existe
        if sheet_service:
            guardar_logs_en_sheets(sheet_service)

        logging.info("✅ Proceso de descarga local finalizado.")
    except Exception as e:
        logging.error(f"❌ Error crítico en ciclo automático: {e}")
        
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


if __name__ == "__main__":
    ejecutar_opcion_4()
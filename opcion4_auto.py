import os
import logging
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2
from download.descargar import proceso_local_descargar_archivos
from base_excel import (
    obtener_conexion_google_sheets,
    guardar_logs_en_sheets
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def ejecutar_opcion_4():
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


if __name__ == "__main__":
    ejecutar_opcion_4()
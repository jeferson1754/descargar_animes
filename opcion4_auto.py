import os
import logging
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2
from download.descargar import proceso_local_descargar_archivos

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def ejecutar_opcion_4():
    download_dir = DOWNLOAD_DIR if os.path.exists(
        DOWNLOAD_DIR) else DOWNLOAD_DIR_2
    print(f"📁 Usando directorio: {download_dir}")

    logging.info(
        "\n--- AUTOMÁTICO: INICIANDO DESCARGA LOCAL DESDE GOOGLE SHEETS (OPCIÓN 4) ---")
    proceso_local_descargar_archivos(download_dir)
    logging.info("✅ Proceso de descarga local finalizado.")


if __name__ == "__main__":
    ejecutar_opcion_4()

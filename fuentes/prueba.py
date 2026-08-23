# pruebas_tioanime.py
import re
import unicodedata
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


import sys
import os

# Agrega la raíz del proyecto al path de Python para evitar errores de importación
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utilidades.navegador import configurar_navegador
from config import DOWNLOAD_DIR_2
from download.descargar import detectar_servidor_descarga,encontrar_boton_descarga,verificar_descarga


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
        # 2. Detectar servidor
        # --------------------------------------------------

        servidor = detectar_servidor_descarga(
            driver
        )

        print(
            f"🌐 Servidor detectado: {servidor}"
        )

        # --------------------------------------------------
        # 3. Validación específica para MEGA (Errores comunes)
        # --------------------------------------------------

        if servidor == "mega":
            print("🔍 Verificando estado del archivo en Mega...")
            try:
            # Damos un par de segundos por si Mega tarda en renderizar el aviso en pantalla
                time.sleep(2)
                
                texto_pagina = driver.page_source.lower()
                
             # Verificamos si aparece el mensaje exacto o variaciones comunes
                if "el archivo ya no está disponible" in texto_pagina or "file no longer available" in texto_pagina:
                    print(f"❌ Error en Mega: El archivo ya no está disponible.")
                    return False
                
                if "archivo no encontrado" in texto_pagina or "file not found" in texto_pagina:
                    print(f"❌ Error en Mega: El archivo no fue encontrado o fue eliminado.")
                    return False
                
                if "cuota de transferencia agotada" in texto_pagina or "bandwidth quota exceeded" in texto_pagina or "quota exceeded" in texto_pagina:
                    print(f"⚠️ Error en Mega: Se ha agotado la cuota de transferencia.")
                    return False
                    
            except Exception as e:
                print(f"⚠️ No se pudo verificar el estado de Mega: {e}")

        # --------------------------------------------------
        # 4. Buscar botón correspondiente
        # --------------------------------------------------

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
 
if __name__ == "__main__":
# 1. Convertirlo en una LISTA de diccionarios (usando corchetes [])
    animes = [
        {
            "nombre": "Tenmaku no Jaadugar Episodio 8",
            "link_descarga": "https://mega.nz/#!cXFwzSJC!JkMylO_o0BJKIgEapPUCx5j1eBddAVJuWtQWiB4feuo"
        },
        {
            "nombre": "Tenmaku no Jaadugar Episodio 9",
            "link_descarga": "https://mega.nz/#!sTkkiRzD!IfMXgbeOIIiBEG1DR7xOuaamBqBrrLo_XKl1JDlIQQ4"
        }
    ]

    # 2. Configuramos el navegador una sola vez fuera del bucle
    driver = configurar_navegador(DOWNLOAD_DIR_2)

    try:
        # 3. Recorremos cada anime de la lista con un bucle for
        for anime in animes:
            print(f"\n🚀 Procesando prueba para: {anime['nombre']}")
            
            hacer_click_en_boton_descarga(
                driver,
                anime["link_descarga"], 
                DOWNLOAD_DIR_2, 
                anime["nombre"]
            )
            
     # Opcional: una breve pausa entre descargas de prueba
        time.sleep(3)
            
    finally:
        # Cerramos el navegador al terminar las pruebas
        driver.quit()
        print("\n🔒 Navegador cerrado.")

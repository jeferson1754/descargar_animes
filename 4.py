import os
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2, SERVIDOR
from animes.buscador import extraer_nombres_anime
import logging

from animes.comparador import (
    obtener_archivos_descargados,
    comparar_descargas
)


from utilidades.archivos import guardar_resultados_animes_txt, guardar_archivos_descargados, guardar_animes_no_descargados, leer_nombres_animes_a_descargar, mover_videos_y_limpiar_carpetas, eliminar_txt, guardar_resultados_animes_json
from animes.comparador import obtener_archivos_descargados, comparar_descargas
from download.descargar import flujo_descarga_animes , proceso_local_descargar_archivos
from base_excel import obtener_conexion_google_sheets, leer_animes_pendientes, verificar_animes_desaparecidos

def procesar_animes(
    download_dir,
    archivo_animes,
    archivo_resultado_descargados,
    archivo_resultado_no_descargados
):
    """
    Función principal que gestiona la verificación de los animes a descargar.

    Args:
        download_dir (str): Directorio de descargas.
        archivo_animes (str): Archivo de animes a descargar.
        archivo_resultado_descargados (str): Archivo donde se guardarán los archivos descargados.
        archivo_resultado_no_descargados (str): Archivo donde se guardarán los animes no descargados.
    """

    mover_videos_y_limpiar_carpetas(
        download_dir,
        download_dir
    )

    animes_a_descargar = leer_nombres_animes_a_descargar(
        archivo_animes
    )
    
    if not animes_a_descargar:
        logging.info("✅ No hay animes pendientes por descargar según la base de datos.")
        # Limpiamos los archivos de registro anteriores
        guardar_animes_no_descargados([], archivo_resultado_no_descargados)
        return False
    # --------------------------------------------------
    # No hay archivos descargados todavía
    # --------------------------------------------------

    logging.info(f"\n📺 Animes pendientes por procesar ({len(animes_a_descargar)}):")
    for anime in animes_a_descargar:
        logging.info(f"   • {anime}")

    # --------------------------------------------------
    # Registrar archivos descargados
    # --------------------------------------------------
    # 2. Registrar la lista directa devuelta por la base de datos como los "pendientes" actuales
    guardar_animes_no_descargados(
        animes_a_descargar,
        archivo_resultado_no_descargados
    )

    # --------------------------------------------------
    # Comparar
    # --------------------------------------------------
# 3. Opcional: Obtener y guardar una lista de los archivos .mp4/.mkv que tienes localmente como respaldo visual
    archivos_locales = obtener_archivos_descargados(download_dir)
    if archivos_locales:
        guardar_archivos_descargados(
            archivos_locales,
            archivo_resultado_descargados
        )


    return bool(animes_a_descargar)


# ============================================================
# MENÚ DE DÍAS
# ============================================================

def menu_dias():
    dias = {
        "1": "Lunes",
        "2": "Martes",
        "3": "Miércoles",
        "4": "Jueves",
        "5": "Viernes",
        "6": "Sábado",
        "7": "Domingo",
        "0": "Volver al menú principal"
    }

    while True:
        print("\n=== SELECCIONE UN DÍA ===")
        for clave, dia in dias.items():
            print(f"{clave}. {dia}")

        opcion = input("Seleccione un día: ").strip()

        if opcion == "0":
            return None

        if opcion in dias:
            dia = dias[opcion]
            return f"{SERVIDOR}Anime/Emision/descargar.php?dias={dia}&enviar2=&accion=Filtro"

        print("❌ Opción inválida.")


# ============================================================
# MENÚ PRINCIPAL MEJORADO
# ============================================================

def menu_principal(download_dir):
    while True:
        print("\n" + "="*40)
        print("=== MENÚ PRINCIPAL DE GESTIÓN DE ANIMES ===")
        print("="*40)
        print("--- 🌐 FASE NUBE Y BÚSQUEDA (Bot) ---")
        print("1. Buscar animes de hoy (Actualizar Google Sheets)")
        print("2. Buscar animes pendientes/faltantes (Actualizar Google Sheets)")
        print("3. Seleccionar un día específico para buscar")
        print("\n--- 📥 FASE LOCAL (Descargas) ---")
        print("4. Descargar pendientes desde Google Sheets (Ejecución Local)")
        print("\n--- 🛠️ UTILIDADES ---")
        print("5. Sacar videos de carpetas de descargas")
        print("0. Salir")
        print("="*40)

        opcion = input("Seleccione una opción: ").strip()

        # Opciones que devuelven URL para el proceso de búsqueda web inicial
        if opcion == "1":
            url = f"{SERVIDOR}Anime/Emision/descargar.php?enviar=&accion=HOY"
            return {"accion": "buscar", "url": url}

        elif opcion == "2":
            url = f"{SERVIDOR}Anime/Emision/descargar.php?faltantes=&accion=HOY"
            return {"accion": "buscar", "url": url}

        elif opcion == "3":
            url = menu_dias()
            if url:
                return {"accion": "buscar", "url": url}

        # Opción 4: Lanza la descarga local directa usando Google Sheets
        elif opcion == "4":
            logging.info("\n--- INICIANDO PROCESO DE DESCARGA LOCAL ---")
            proceso_local_descargar_archivos(download_dir)
            # Retorna un indicador para que el bucle principal sepa que no debe abrir URL web
            return {"accion": "menu_continuar"}

        # Opción 5: Utilidad de archivos
        elif opcion == "5":
            mover_videos_y_limpiar_carpetas(
                download_dir,
                download_dir
            )
            logging.info("✅ Limpieza de carpetas completada.")

        elif opcion == "0":
            logging.info("👋 Saliendo del programa. ¡Hasta luego!")
            return None

        else:
            logging.info("❌ Opción inválida. Por favor, ingrese un número del 0 al 5.")


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================


def menu():

    # Definir ambas rutas
    ruta_1 = DOWNLOAD_DIR
    ruta_2 = DOWNLOAD_DIR_2

    # Verificar si la primera ruta existe; si no, usar la segunda
    if os.path.exists(ruta_1):
        download_dir = ruta_1
        print(f"📁 Usando ruta principal: {download_dir}")
    else:
        download_dir = ruta_2
        print(
            f"⚠️ La ruta principal no existe. Usando ruta alternativa: {download_dir}")

  # 1. Obtener la respuesta estructurada del menú principal
    resultado_menu = menu_principal(download_dir)

    # Si se seleccionó salir (None) o la respuesta está vacía
    if not resultado_menu:
        print("No se seleccionó ninguna opción válida. Volviendo al menú principal...")
        return menu()

    accion = resultado_menu.get("accion")

    # Si la opción elegida fue la descarga local directa desde Google Sheets (Opción 4)
    if accion == "menu_continuar":
        print("\nVolviendo al menú principal...")
        return menu()

    # Si la opción elegida requiere hacer web scraping (Opciones 1, 2 o 3)
    if accion == "buscar":
        url = resultado_menu.get("url")
        
        # Extraer y mostrar los nombres de los animes
        nombres_anime = extraer_nombres_anime(url, download_dir)
        
        if not nombres_anime:
            logging.error("❌ No se encontraron animes para procesar en esta selección.")
            eliminar_txt()
            return menu()
        
        # 2. Obtener conexión y leer lo que ya está en Google Sheets
        sheet_service = obtener_conexion_google_sheets()
        if sheet_service:
            animes_previos_sheets = leer_animes_pendientes(sheet_service)
        
            # 3. EJECUTAR LA VALIDACIÓN: Marcar como completados los que ya no salgan en la web
            verificar_animes_desaparecidos(sheet_service, animes_previos_sheets, nombres_anime)

        archivo_animes = "resultados_anime.txt"
        archivo_resultado_descargados = "archivos_descargados.txt"
        archivo_resultado_no_descargados = "animes_no_descargados.txt"

        # Guardar los nombres en el archivo de texto
        guardar_resultados_animes_json(nombres_anime, archivo_animes)

        logging.info(f"Cantidad de animes extraídos: {len(nombres_anime)}")
        for nombre in nombres_anime:
            logging.info(nombre)
        logging.info(f"Datos guardados en '{archivo_animes}'")

        # Procesar animes detectados
        procesar_animes(
            download_dir, 
            archivo_animes, 
            archivo_resultado_descargados,
            archivo_resultado_no_descargados
        )

        # Validar si hay animes pendientes para buscar enlaces y actualizar Google Sheets
        if not os.path.exists(archivo_resultado_no_descargados) or os.path.getsize(archivo_resultado_no_descargados) == 0:
            logging.info("No hay nuevos animes pendientes para buscar videos.")
        else:
            continuar_descarga = flujo_descarga_animes(
                archivo_resultado_no_descargados, download_dir
            )

            if continuar_descarga is False:
                eliminar_txt()
                print("\nVolviendo al menú principal...")
                return menu()

        eliminar_txt()


if __name__ == "__main__":
    menu()

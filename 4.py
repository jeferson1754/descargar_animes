import os
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2, SERVIDOR
from animes.buscador import extraer_nombres_anime

from animes.comparador import (
    obtener_archivos_descargados,
    comparar_descargas
)


from utilidades.archivos import guardar_resultados_animes_txt, guardar_archivos_descargados, guardar_animes_no_descargados, leer_nombres_animes_a_descargar, mover_videos_y_limpiar_carpetas, eliminar_txt, guardar_resultados_animes_json
from animes.comparador import obtener_archivos_descargados, comparar_descargas
from download.descargar import flujo_descarga_animes


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
        print("✅ No hay animes pendientes por descargar según la base de datos.")
        # Limpiamos los archivos de registro anteriores
        guardar_animes_no_descargados([], archivo_resultado_no_descargados)
        return False
    # --------------------------------------------------
    # No hay archivos descargados todavía
    # --------------------------------------------------

    print(f"\n📺 Animes pendientes por procesar ({len(animes_a_descargar)}):")
    for anime in animes_a_descargar:
        print(f"   • {anime}")

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

            print(
                f"{clave}. {dia}"
            )

        opcion = input(
            "Seleccione un día: "
        ).strip()

        if opcion == "0":
            return None

        if opcion in dias:
            dia = dias[opcion]
            # Corrección: Uso de f-string para construir la URL de forma limpia
            return f"{SERVIDOR}Anime/Emision/descargar.php?dias={dia}&enviar2=&accion=Filtro"

        print("❌ Opción inválida.")

        print(
            "❌ Opción inválida."
        )


# ============================================================
# MENÚ PRINCIPAL
# ============================================================

def menu_principal(download_dir):

    while True:

        print("\n=== MENÚ DE OPCIONES ===")

        print("1. Descargar animes de hoy")
        print("2. Descargar animes pendientes")
        print("3. Seleccionar un día")
        print("4. Sacar videos de carpetas de descargas")
        print("0. Salir")

        opcion = input(
            "Seleccione una opción: "
        ).strip()

        if opcion == "1":
            # Corrección: Formateo con f-string para devolver la cadena completa
            return f"{SERVIDOR}Anime/Emision/descargar.php?enviar=&accion=HOY"

        elif opcion == "2":
            # Corrección: Formateo con f-string (evita el fallo por falta de '+')
            return f"{SERVIDOR}Anime/Emision/descargar.php?faltantes=&accion=HOY"

        elif opcion == "3":
            url = menu_dias()
            if url:
                return url

        elif opcion == "4":

            mover_videos_y_limpiar_carpetas(
                download_dir,
                download_dir
            )

        elif opcion == "0":

            return None

        else:

            print(
                "❌ Opción inválida."
            )


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

    # URL de la página a analizar
    url = menu_principal(download_dir)

    if url is None or url == "":
        print("No se seleccionó ninguna opción válida. Volviendo al menú principal...")
        menu()

    # Extraer y mostrar los nombres de los animes
    nombres_anime = extraer_nombres_anime(url, download_dir)

    # Guardar los nombres en un archivo .txt
    guardar_resultados_animes_json(nombres_anime, "resultados_anime.txt")

    # Mostrar conteo y los nombres en la consola
    conteo_anime = len(nombres_anime)

    # Ruta de la carpeta de descargas y archivo de animes
    archivo_animes = "resultados_anime.txt"
    archivo_resultado_descargados = "archivos_descargados.txt"
    archivo_resultado_no_descargados = "animes_no_descargados.txt"

    print(f"Cantidad de animes extraídos: {conteo_anime}")
    for nombre in nombres_anime:
        print(nombre)

    print(f"Datos guardados en 'resultados_anime.txt'")

    # Ejecutar la función principal
    procesar_animes(download_dir, archivo_animes, archivo_resultado_descargados,
                    archivo_resultado_no_descargados)

    # Ejecutar función principal solo si hay animes por descargar
    if not os.path.exists(archivo_resultado_no_descargados) or os.path.getsize(archivo_resultado_no_descargados) == 0:
        print("No se ejecuta la funcion buscar videos de anime")
    else:
        continuar_descarga = flujo_descarga_animes(
            archivo_resultado_no_descargados, download_dir)

        if continuar_descarga is False:
            eliminar_txt()
            print("\nVolviendo al menú principal...")
            return menu()

    eliminar_txt()


if __name__ == "__main__":
    menu()

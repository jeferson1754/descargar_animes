import os
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2
from animes.buscador import extraer_nombres_anime

from animes.comparador import (
    obtener_archivos_descargados,
    comparar_descargas
)


from utilidades.archivos import guardar_resultados_animes_txt, guardar_archivos_descargados, guardar_animes_no_descargados, leer_nombres_animes_a_descargar, mover_videos_y_limpiar_carpetas, eliminar_txt
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

    archivos_descargados = obtener_archivos_descargados(
        download_dir
    )

    animes_a_descargar = leer_nombres_animes_a_descargar(
        archivo_animes
    )

    if not animes_a_descargar:

        print(
            "❌ No se encontraron animes para descargar."
        )

        return False

    # --------------------------------------------------
    # No hay archivos descargados todavía
    # --------------------------------------------------

    if not archivos_descargados:

        print(
            "📁 No se encontraron archivos descargados."
        )

        guardar_animes_no_descargados(
            animes_a_descargar,
            archivo_resultado_no_descargados
        )

        return True

    # --------------------------------------------------
    # Registrar archivos descargados
    # --------------------------------------------------

    guardar_archivos_descargados(
        archivos_descargados,
        archivo_resultado_descargados
    )

    # --------------------------------------------------
    # Comparar
    # --------------------------------------------------

    animes_no_descargados = comparar_descargas(
        animes_a_descargar,
        archivos_descargados
    )

    if not animes_no_descargados:

        print(
            "✅ Todos los animes ya han sido descargados."
        )

    else:

        print(
            "\n📺 Animes pendientes:"
        )

        for anime in animes_no_descargados:

            print(
                f"   • {anime}"
            )

    # --------------------------------------------------
    # Guardar pendientes
    # --------------------------------------------------



    return bool(animes_no_descargados)

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

            return (
                "https://inventarioncc.infinityfreeapp.com/"
                f"Anime/Emision/?dias={dia}"
                "&enviar2=&accion=Filtro"
            )

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

            return (
                "https://inventarioncc.infinityfreeapp.com/"
                "Anime/Emision/?enviar=&accion=HOY"
            )

        elif opcion == "2":

            return (
                "https://inventarioncc.infinityfreeapp.com/"
                "Anime/Emision/?faltantes=&accion=HOY"
            )

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

    # --------------------------------------------------
    # Seleccionar ruta de descarga
    # --------------------------------------------------

    if os.path.exists(DOWNLOAD_DIR):

        download_dir = DOWNLOAD_DIR

        print(
            f"📁 Usando ruta principal:\n"
            f"{download_dir}"
        )

    elif os.path.exists(DOWNLOAD_DIR_2):

        download_dir = DOWNLOAD_DIR_2

        print(
            "⚠️ La ruta principal no existe."
        )

        print(
            f"📁 Usando ruta alternativa:\n"
            f"{download_dir}"
        )

    else:

        print(
            "❌ No se encontró ninguna ruta de descarga."
        )

        return

    # --------------------------------------------------
    # Menú
    # --------------------------------------------------

    url = menu_principal(
        download_dir
    )

    if not url:

        print(
            "👋 Programa finalizado."
        )

        return

    # --------------------------------------------------
    # Extraer animes
    # --------------------------------------------------

    print(
        "\n🔎 Analizando programación..."
    )

    nombres_anime = extraer_nombres_anime(
        url,
        download_dir
    )

    if not nombres_anime:

        print(
            "❌ No se encontraron animes."
        )

        return

    # --------------------------------------------------
    # Guardar resultados
    # --------------------------------------------------

    archivo_animes = "resultados_anime.txt"

    archivo_resultado_descargados = (
        "archivos_descargados.txt"
    )

    archivo_resultado_no_descargados = (
        "animes_no_descargados.txt"
    )

    guardar_resultados_animes_txt(
        nombres_anime,
        archivo_animes
    )

    # --------------------------------------------------
    # Mostrar animes
    # --------------------------------------------------

    print(
        f"\n📺 Animes encontrados: "
        f"{len(nombres_anime)}"
    )

    for indice, nombre in enumerate(
        nombres_anime,
        1
    ):

        print(
            f"{indice}. {nombre}"
        )

    # --------------------------------------------------
    # Determinar pendientes
    # --------------------------------------------------

    hay_pendientes = procesar_animes(
        download_dir,
        archivo_animes,
        archivo_resultado_descargados,
        archivo_resultado_no_descargados
    )

    if not hay_pendientes:

        eliminar_txt()

        print(
            "\nNo hay nada que descargar."
        )

        return

    # --------------------------------------------------
    # Buscar y descargar
    # --------------------------------------------------

    continuar = flujo_descarga_animes(
        archivo_resultado_no_descargados,
        download_dir
    )

    # --------------------------------------------------
    # Si se cancela, volver al menú
    # --------------------------------------------------

    if continuar is False:

        print(
            "\n↩️ Volviendo al menú principal..."
        )

        eliminar_txt()

        return menu()

    # --------------------------------------------------
    # Limpieza
    # --------------------------------------------------

    eliminar_txt()


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    menu()

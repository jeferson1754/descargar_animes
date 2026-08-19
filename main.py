# main.py

from config import DOWNLOAD_DIR, FUENTES_ANIME

from animes.buscador import buscar_en_fuentes

from utilidades.archivos import (
    crear_directorio,
    obtener_videos
)


def ejecutar():

    print("=" * 60)
    print("        SISTEMA AUTOMÁTICO DE ANIMES")
    print("=" * 60)

    # --------------------------------------------------
    # 1. Comprobar carpeta de descargas
    # --------------------------------------------------

    crear_directorio(DOWNLOAD_DIR)

    print(
        f"\n📁 Carpeta de descargas:"
        f"\n{DOWNLOAD_DIR}"
    )

    # --------------------------------------------------
    # 2. Obtener animes pendientes
    # --------------------------------------------------

    animes_pendientes = obtener_animes_pendientes()

    if not animes_pendientes:

        print(
            "\n✅ No hay animes pendientes."
        )

        return

    print(
        f"\n📺 Animes pendientes: "
        f"{len(animes_pendientes)}"
    )

    for anime in animes_pendientes:

        print(
            f"   • {anime}"
        )

    # --------------------------------------------------
    # 3. Buscar los animes en las fuentes
    # --------------------------------------------------

    print(
        "\n🔎 Buscando en las fuentes..."
    )

    resultados = buscar_en_fuentes(
        animes_pendientes,
        FUENTES_ANIME
    )

    if not resultados:

        print(
            "\n❌ No se encontraron resultados."
        )

        return

    # --------------------------------------------------
    # 4. Mostrar resultados
    # --------------------------------------------------

    print(
        "\n✅ Resultados encontrados:"
    )

    for resultado in resultados:

        print(
            f"\n📺 {resultado.get('nombre')}"
        )

        print(
            f"   Fuente: "
            f"{resultado.get('enlace')}"
        )

        print(
            f"   Episodio: "
            f"{resultado.get('episodio')}"
        )

        print(
            f"   Video: "
            f"{resultado.get('link_video')}"
        )

        print(
            f"   Descarga: "
            f"{resultado.get('link_descarga')}"
        )

    # --------------------------------------------------
    # 5. Descargar
    # --------------------------------------------------

    print(
        "\n⬇️ Iniciando sistema de descargas..."
    )

    iniciar_descargas(
        resultados,
        DOWNLOAD_DIR
    )

    # --------------------------------------------------
    # 6. Comprobar archivos descargados
    # --------------------------------------------------

    videos = obtener_videos(
        DOWNLOAD_DIR
    )

    print(
        "\n📦 Videos actualmente en la carpeta:"
    )

    for video in videos:

        print(
            f"   • {video}"
        )

    print(
        "\n" + "=" * 60
    )

    print(
        "✅ PROCESO FINALIZADO"
    )

    print(
        "=" * 60
    )


# ============================================================
# FUNCIONES DEL FLUJO PRINCIPAL
# ============================================================

def obtener_animes_pendientes():

    """
    Obtiene los animes que todavía necesitan descargarse.

    Por ahora esta función puede utilizar
    tu sistema actual de TXT.

    Más adelante puede obtenerlos desde:
        - TXT
        - Excel
        - base de datos
        - calendario
        - API
    """

    from utilidades.archivos import leer_txt

    archivo = "animes_no_descargados.txt"

    return leer_txt(
        archivo
    )


def iniciar_descargas(
    resultados,
    download_dir
):

    """
    Envía los resultados al sistema de descargas.
    """

    from descargas.descargar import hacer_click_en_boton_descarga

    hacer_click_en_boton_descarga(
        resultados,
        DOWNLOAD_DIR
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    try:

        ejecutar()

    except KeyboardInterrupt:

        print(
            "\n\n⚠️ Proceso detenido por el usuario."
        )

    except Exception as e:

        print(
            "\n❌ ERROR NO CONTROLADO:"
        )

        print(e)
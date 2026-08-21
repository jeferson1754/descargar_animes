import re
import os

from utilidades.archivos import extraer_episodio_archivo


def normalizar_nombre(nombre):
    """
    Normaliza el nombre del anime para que sea comparable con los nombres de archivo.
    Elimina los espacios y caracteres no alfabéticos y convierte a minúsculas.

    Args:
        nombre (str): Nombre del anime a normalizar.

    Returns:
        str: Nombre normalizado del anime.
    """
    # Eliminar espacios, guiones, guiones bajos y convertir a minúsculas
    nombre_normalizado = re.sub(r'[^a-zA-Z0-9]', '', nombre.lower())
    return nombre_normalizado


def obtener_archivos_descargados(download_dir):
    """
    Obtiene una lista de los archivos descargados en el directorio de descargas.

    Args:
        download_dir (str): Directorio de descargas.

    Returns:
        list: Lista de nombres de archivos en el directorio de descargas.
    """
    try:
        archivos_descargados = os.listdir(download_dir)
        archivos_mp4 = [
            archivo for archivo in archivos_descargados if archivo.endswith(".mp4")]
        return archivos_mp4
    except FileNotFoundError:
        print("El directorio de descargas no se encontró.")
        return []


def comparar_descargas(
    animes_a_descargar,
    archivos_descargados
):
    """
    Compara animes pendientes con los archivos descargados,
    teniendo en cuenta el episodio específico.

    Cada anime debe tener:

        {
            "nombre": "...",
            "episodio_buscado": 8,
            ...
        }

    Devuelve únicamente los animes cuyo episodio pendiente
    todavía no existe localmente.
    """

    animes_no_descargados = []

    # --------------------------------------------------
    # Crear una estructura con los archivos existentes
    # --------------------------------------------------

    archivos_info = []

    for archivo in archivos_descargados:

        nombre_archivo_normalizado = normalizar_nombre(
            archivo
        )

        episodio = extraer_episodio_archivo(
            archivo
        )

        archivos_info.append({
            "archivo": archivo,
            "nombre_normalizado": nombre_archivo_normalizado,
            "episodio": episodio
        })

    # --------------------------------------------------
    # Analizar cada anime pendiente
    # --------------------------------------------------

    for anime in animes_a_descargar:

        nombre_anime = anime["nombre"]

        episodio_buscado = anime.get(
            "episodio_buscado"
        )

        nombre_normalizado = normalizar_nombre(
            nombre_anime
        )

        encontrado = False

        for archivo in archivos_info:

            # El nombre del anime debe coincidir
            if nombre_normalizado not in archivo[
                "nombre_normalizado"
            ]:
                continue

            # El episodio debe coincidir
            if archivo["episodio"] == episodio_buscado:

                encontrado = True

                print(
                    f"✅ Ya descargado: "
                    f"{nombre_anime} "
                    f"Episodio {episodio_buscado}"
                )

                break

        if not encontrado:

            print(
                f"⬇️ Pendiente: "
                f"{nombre_anime} "
                f"Episodio {episodio_buscado}"
            )

            animes_no_descargados.append(
                anime
            )

    return animes_no_descargados
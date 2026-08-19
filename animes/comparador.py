import re
import os

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


def comparar_descargas(animes_a_descargar, archivos_descargados):
    """
    Compara los animes a descargar con los archivos descargados para evitar duplicados.

    Args:
        animes_a_descargar (list): Lista de animes que se quieren descargar.
        archivos_descargados (list): Lista de archivos ya descargados.

    Returns:
        list: Lista de animes que no han sido descargados.
    """
    animes_no_descargados = []
    for anime in animes_a_descargar:
        # Normalizar el nombre del anime a comparar
        anime_normalizado = normalizar_nombre(anime)

        # Comparar el nombre normalizado con los archivos descargados
        encontrado = False
        for archivo in archivos_descargados:
            archivo_normalizado = normalizar_nombre(archivo)

            # Si el nombre normalizado del anime está en el archivo descargado
            if anime_normalizado in archivo_normalizado:
                encontrado = True
                break

        if not encontrado:
            animes_no_descargados.append(anime)

    return animes_no_descargados



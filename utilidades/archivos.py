# utilidades/archivos.py
import json
import re
import os
import shutil


def guardar_resultados_animes_txt(animes, filename):
    """
    Guarda la información de los animes en un archivo TXT.

    Cada anime contiene:
    - nombre
    - episodio_actual
    - episodios_totales
    - pendientes
    - episodio_buscado
    """

    try:
        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as file:

            for anime in animes:

                file.write(
                    f"Nombre: {anime['nombre']}\n"
                )

                file.write(
                    f"Episodio actual: "
                    f"{anime['episodio_actual']}\n"
                )

                file.write(
                    f"Episodios totales: "
                    f"{anime['episodios_totales']}\n"
                )

                file.write(
                    f"Pendientes: "
                    f"{anime['pendientes']}\n"
                )

                file.write(
                    f"Episodio buscado: "
                    f"{anime['episodio_buscado']}\n"
                )

                file.write(
                    "-" * 50 + "\n"
                )

        print(
            f"✅ Resultados guardados en: {filename}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Error guardando resultados: {e}"
        )

        return False


def leer_nombres_y_enlaces_desde_txt(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            contenido = file.read()

        # Utilizar expresiones regulares para extraer los nombres y enlaces
        videos = []
        patrones = re.findall(
            r'"nombre": "(.*?)".*?"link_video": "(.*?)".*?"link_descarga": "(.*?)"', contenido, re.DOTALL)

        for match in patrones:
            nombre, enlace_video, enlace_descarga = match
            videos.append(
                {'nombre': nombre, 'link_video': enlace_video, 'link_descarga': enlace_descarga})

        print(f"Videos leídos desde el archivo: {videos}")
        return videos

    except FileNotFoundError:
        print(f"El archivo '{filename}' no fue encontrado.")
        return []


def guardar_animes_no_descargados(
    animes_no_descargados,
    archivo_salida
):
    """
    Guarda los animes pendientes junto con su información
    de episodios en un archivo JSON.

    Cada elemento puede contener:
        nombre
        episodio_actual
        episodios_totales
        pendientes
        episodio_buscado
    """

    try:
        directorio = os.path.dirname(archivo_salida)

        if directorio:
            os.makedirs(
                directorio,
                exist_ok=True
            )

        with open(
            archivo_salida,
            "w",
            encoding="utf-8"
        ) as archivo:

            json.dump(
                animes_no_descargados,
                archivo,
                ensure_ascii=False,
                indent=4
            )

        print(
            f"✅ Animes pendientes guardados en:\n"
            f"{archivo_salida}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Error al guardar los animes pendientes: {e}"
        )

        return False


def guardar_resultados_videos_txt(videos, filename):
    """Guarda los detalles de los videos, incluyendo el enlace de descarga, en un archivo de texto."""
    with open(filename, 'w', encoding='utf-8') as file:
        # Escribir el conteo de videos encontrados
        file.write(f"Cantidad de videos encontrados: {len(videos)}\n\n")

        # Escribir los detalles de cada video
        for video in videos:
            file.write(f'"nombre": "{video["nombre"]}",\n')
            file.write(
                f'"link_descarga": "{video.get("link_descarga", "N/A")}"\n')
            file.write("-" * 40 + "\n")


def leer_nombres_desde_txt(filename):
    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:

            animes = json.load(file)

        if not isinstance(animes, list):
            print(
                f"❌ El archivo '{filename}' "
                "no contiene una lista de animes."
            )
            return []

        return animes

    except FileNotFoundError:
        print(
            f"❌ El archivo '{filename}' "
            "no fue encontrado."
        )
        return []

    except json.JSONDecodeError as e:
        print(
            f"❌ Error leyendo el JSON '{filename}': {e}"
        )
        return []

    except Exception as e:
        print(
            f"❌ Error leyendo '{filename}': {e}"
        )
        return []


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


def guardar_archivos_descargados(archivos, archivo_salida):
    """
    Guarda los nombres de los archivos descargados en un archivo de texto.

    Args:
        archivos (list): Lista de archivos a guardar.
        archivo_salida (str): Nombre del archivo de salida donde se guardarán los nombres.
    """
    with open(archivo_salida, 'w', encoding='utf-8') as f:
        for archivo in archivos:
            f.write(archivo + "\n")


# ============================================================
# CARPETAS
# ============================================================

def crear_directorio(directorio):
    """
    Crea un directorio si no existe.
    """

    if not os.path.exists(directorio):
        os.makedirs(directorio)

        print(
            f"📁 Directorio creado: {directorio}"
        )

    return directorio


def existe_directorio(directorio):
    """
    Comprueba si existe un directorio.
    """

    return os.path.isdir(directorio)


# ============================================================
# ARCHIVOS TXT
# ============================================================

def leer_txt(filename):
    """
    Lee un archivo TXT y devuelve una lista de líneas
    sin líneas vacías.
    """

    try:

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as archivo:

            return [
                linea.strip()
                for linea in archivo
                if linea.strip()
            ]

    except FileNotFoundError:

        print(
            f"⚠️ No existe el archivo: {filename}"
        )

        return []


def escribir_txt(filename, datos):
    """
    Escribe una lista de datos en un archivo TXT.
    """

    try:

        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as archivo:

            for dato in datos:

                archivo.write(
                    f"{dato}\n"
                )

        return True

    except Exception as e:

        print(
            f"❌ Error escribiendo {filename}: {e}"
        )

        return False


def agregar_txt(filename, texto):
    """
    Agrega una línea al final de un TXT.
    """

    try:

        with open(
            filename,
            "a",
            encoding="utf-8"
        ) as archivo:

            archivo.write(
                f"{texto}\n"
            )

        return True

    except Exception as e:

        print(
            f"❌ Error agregando al archivo: {e}"
        )

        return False


# ============================================================
# LISTAR ARCHIVOS
# ============================================================

def listar_archivos(directorio):
    """
    Devuelve todos los archivos de un directorio.
    """

    if not os.path.isdir(directorio):
        return []

    return [
        archivo
        for archivo in os.listdir(directorio)
        if os.path.isfile(
            os.path.join(
                directorio,
                archivo
            )
        )
    ]


def listar_archivos_por_extension(
    directorio,
    extensiones
):
    """
    Devuelve archivos que tengan determinadas extensiones.

    Ejemplo:

        listar_archivos_por_extension(
            carpeta,
            [".mp4", ".mkv"]
        )
    """

    if not os.path.isdir(directorio):
        return []

    extensiones = tuple(
        extension.lower()
        for extension in extensiones
    )

    return [
        archivo
        for archivo in listar_archivos(directorio)
        if archivo.lower().endswith(
            extensiones
        )
    ]


# ============================================================
# VIDEOS
# ============================================================

def obtener_videos(directorio):
    """
    Obtiene los videos existentes en una carpeta.
    """

    extensiones_video = (
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv"
    )

    return listar_archivos_por_extension(
        directorio,
        extensiones_video
    )


# ============================================================
# MOVER ARCHIVOS
# ============================================================

def mover_archivo(origen, destino):
    """
    Mueve un archivo.
    """

    try:

        crear_directorio(
            os.path.dirname(destino)
        )

        shutil.move(
            origen,
            destino
        )

        print(
            f"📦 Movido: {origen} → {destino}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Error moviendo archivo: {e}"
        )

        return False


def mover_videos(
    directorio_origen,
    directorio_destino
):
    """
    Busca videos dentro de un directorio
    y los mueve al directorio destino.
    """

    crear_directorio(
        directorio_destino
    )

    videos_movidos = []

    for root, dirs, files in os.walk(
        directorio_origen
    ):

        # Evitar procesar el destino
        if os.path.abspath(root) == os.path.abspath(
            directorio_destino
        ):
            continue

        for archivo in files:

            if not archivo.lower().endswith(
                (
                    ".mp4",
                    ".mkv",
                    ".avi",
                    ".mov",
                    ".wmv"
                )
            ):
                continue

            origen = os.path.join(
                root,
                archivo
            )

            destino = os.path.join(
                directorio_destino,
                archivo
            )

            # Evitar sobrescribir
            if os.path.exists(destino):

                print(
                    f"⚠️ Ya existe: {archivo}"
                )

                continue

            if mover_archivo(
                origen,
                destino
            ):

                videos_movidos.append(
                    archivo
                )

    return videos_movidos


# ============================================================
# LIMPIEZA
# ============================================================

def eliminar_carpetas_vacias(
    directorio
):
    """
    Elimina carpetas vacías dentro de un directorio.
    """

    for root, dirs, files in os.walk(
        directorio,
        topdown=False
    ):

        # No eliminar la carpeta raíz
        if os.path.abspath(root) == os.path.abspath(
            directorio
        ):
            continue

        if not os.listdir(root):

            try:

                os.rmdir(root)

                print(
                    f"🗑️ Carpeta eliminada: {root}"
                )

            except OSError as e:

                print(
                    f"⚠️ No se pudo eliminar "
                    f"{root}: {e}"
                )


def limpiar_carpetas_descarga(
    directorio
):
    """
    Mueve videos y elimina carpetas vacías.
    """

    mover_videos(
        directorio,
        directorio
    )

    eliminar_carpetas_vacias(
        directorio
    )


def guardar_resultados_animes_json(animes, filename):
    """
    Guarda la información completa de los animes en JSON.
    """

    try:
        directorio = os.path.dirname(filename)

        if directorio:
            os.makedirs(
                directorio,
                exist_ok=True
            )

        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as archivo:

            json.dump(
                animes,
                archivo,
                ensure_ascii=False,
                indent=4
            )

        print(
            f"✅ Animes guardados en: {filename}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Error guardando JSON: {e}"
        )

        return False


def leer_nombres_animes_a_descargar(archivo_animes):
    """
    Lee los animes y toda su información desde un archivo JSON.

    Retorna:
        list: Lista de diccionarios con la información de cada anime.
    """

    try:

        with open(
            archivo_animes,
            "r",
            encoding="utf-8"
        ) as archivo:

            animes = json.load(
                archivo
            )

        if not isinstance(animes, list):

            print(
                "❌ El archivo no contiene "
                "una lista válida de animes."
            )

            return []

        return animes

    except FileNotFoundError:

        print(
            f"❌ No se encontró el archivo: "
            f"{archivo_animes}"
        )

        return []

    except json.JSONDecodeError as e:

        print(
            f"❌ El JSON tiene un formato inválido: "
            f"{e}"
        )

        return []

    except Exception as e:

        print(
            f"❌ Error leyendo animes: {e}"
        )

        return []


def mover_videos_y_limpiar_carpetas(directorio_origen, directorio_destino):
    """
    Mueve todos los videos encontrados en subcarpetas al directorio_destino
    y elimina las carpetas de origen que hayan quedado vacías.
    """
    extensiones_video = ('.mp4', '.mkv', '.avi', '.mov', '.wmv')

    if not os.path.exists(directorio_destino):
        os.makedirs(directorio_destino)

    # 1. Mover los archivos
    print("--- Moviendo archivos ---")
    for root, dirs, files in os.walk(directorio_origen):
        # Evitar procesar el mismo directorio destino si está dentro del origen
        if os.path.abspath(root) == os.path.abspath(directorio_destino):
            continue

        for file in files:
            if file.lower().endswith(extensiones_video):
                origen = os.path.join(root, file)
                destino = os.path.join(directorio_destino, file)

                if not os.path.exists(destino):
                    shutil.move(origen, destino)
                    print(f"✅ Movido: {file}")
                else:
                    print(f"⚠️ Ya existe: {file}")

    # 2. Eliminar carpetas vacías
    # Usamos topdown=False para eliminar subcarpetas antes que la carpeta padre
    print("\n--- Limpiando carpetas vacías ---")
    for root, dirs, files in os.walk(directorio_origen, topdown=False):
        # No borrar el directorio raíz de origen ni el directorio destino
        if os.path.abspath(root) == os.path.abspath(directorio_origen):
            continue
        if os.path.abspath(root) == os.path.abspath(directorio_destino):
            continue

        # Si la carpeta está vacía, borrarla
        if not os.listdir(root):
            try:
                os.rmdir(root)
                print(f"🗑️ Carpeta eliminada: {root}")
            except OSError as e:
                print(f"❌ No se pudo borrar {root}: {e}")

    print("\nProceso completado.")


def eliminar_txt():
    """Elimina todos los archivos en formato TXT en la carpeta actual excepto 'requirements.txt' tras confirmación."""
  # Filtrar archivos .txt excluyendo 'requirements.txt'
    archivos_txt = [archivo for archivo in os.listdir(
        '.') if archivo.endswith('.txt') and archivo != 'requirements.txt']

    if not archivos_txt:
        print("No se encontraron archivos TXT en la carpeta actual (excepto 'requirements.txt').")
        return

    print("Se encontraron los siguientes TXT (excepto 'requirements.txt'):")
    for archivo in archivos_txt:
        print(archivo)

    confirmar = input(
        "¿Estás seguro de que deseas eliminar estos archivos? (Presiona Enter para confirmar): ")

    if confirmar == '':
        for archivo in archivos_txt:
            try:
                os.remove(archivo)
                print(f"Eliminado: {archivo}")
            except Exception as e:
                print(f"No se pudo eliminar {archivo}: {e}")
    else:
        print("Eliminación cancelada.")


def extraer_episodio_archivo(nombre_archivo):
    """
    Extrae el número de episodio desde el nombre del archivo.

    Ejemplos:
        'Reiwa no Dara-san 7.mp4' -> 7
        'Reiwa no Dara-san - 8.mp4' -> 8
        'Anime_X_Episodio_12.mp4' -> 12

    Retorna:
        int o None
    """

    nombre = os.path.splitext(nombre_archivo)[0]

    patrones = [
        r'[Ee]pisodio[\s._-]*(\d+)$',
        r'[\s._-]+(\d+)$'
    ]

    for patron in patrones:

        coincidencia = re.search(
            patron,
            nombre
        )

        if coincidencia:
            return int(
                coincidencia.group(1)
            )

    return None

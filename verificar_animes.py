import requests
from bs4 import BeautifulSoup


def leer_nombres_desde_txt(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            # Leer las líneas y eliminar las líneas vacías o las líneas que no contienen datos relevantes
            nombres = [line.strip()
                       for line in file.readlines() if line.strip()]
        return nombres
    except FileNotFoundError:
        print(f"El archivo '{filename}' no fue encontrado.")
        return []


def buscar_videos(url, nombres_videos):
    try:
        # Obtener el contenido de la página web
        respuesta = requests.get(url)
        respuesta.raise_for_status()  # Verifica si la solicitud fue exitosa
        soup = BeautifulSoup(respuesta.text, 'html.parser')

        # Lista para almacenar los enlaces de los videos encontrados
        videos_encontrados = []

        # Buscar todos los enlaces en la página
        for enlace in soup.find_all('a', href=True):
            texto = enlace.text.strip()
            for nombre in nombres_videos:
                if nombre.lower() in texto.lower():  # Comparar ignorando mayúsculas y minúsculas
                    videos_encontrados.append({
                        'nombre': texto,
                        'enlace': enlace['href']
                    })

        return videos_encontrados

    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la página: {e}")
        return []


def guardar_resultados_txt(videos, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        # Escribir el conteo de videos encontrados
        file.write(f"Cantidad de videos encontrados: {len(videos)}\n\n")

        # Escribir los detalles de cada video
        for video in videos:
            file.write(f'"nombre": "{video["nombre"]}",\n')
            file.write(
                f'"link_video": "https://tioanime.com{video["enlace"]}"\n')
            file.write("-" * 40 + "\n")


# URL de la página web
url_tioanime = "https://tioanime.com/"

# Leer los nombres de los videos desde el archivo 'resultados_anime.txt'
nombres_videos = leer_nombres_desde_txt("resultados_anime.txt")

# Buscar los videos en la página
videos = buscar_videos(url_tioanime, nombres_videos)

# Guardar los resultados en un archivo .txt
guardar_resultados_txt(videos, "resultados_videos.txt")

# Mostrar resultados
if videos:
    print("Videos encontrados:")
    for video in videos:
        print(f"Nombre: {video['nombre']} - Enlace: https://tioanime.com{video['enlace']}")
else:
    print("No se encontraron videos con los nombres especificados.")

print(f"Datos guardados en 'resultados_videos.txt'")

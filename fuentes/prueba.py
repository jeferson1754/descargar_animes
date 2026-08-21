# pruebas_tioanime.py
import re
import unicodedata

from fuentes.tioanime import buscar_videos_tioanime, obtener_ultimo_episodio
from config import DOWNLOAD_DIR, DOWNLOAD_DIR_2
from utilidades.navegador import configurar_navegador



URL_TIOANIME = "https://tioanime.com/anime/"

def convertir_nombre_url(nombre):
    """
    Convierte un nombre de anime a formato slug para URL.

    Ejemplo:
        'Sayonara Lara' -> 'sayonara-lara'
    """

    # Minúsculas
    nombre = nombre.lower()

    # Eliminar tildes
    nombre = unicodedata.normalize(
        "NFKD",
        nombre
    ).encode(
        "ascii",
        "ignore"
    ).decode(
        "ascii"
    )

    # Reemplazar todo lo que no sea letra o número por "-"
    nombre = re.sub(
        r"[^a-z0-9]+",
        "-",
        nombre
    )

    # Eliminar "-" del principio y final
    nombre = nombre.strip("-")

    return nombre


def prueba():

    nombres = [
        "Sayonara Lara 7",
    ]

    print("=" * 60)
    print("PRUEBA DE BÚSQUEDA EN TIOANIME")
    print("=" * 60)


    driver = configurar_navegador(DOWNLOAD_DIR)
    
    try:
    
        for nombre in nombres:

            nombre_url = convertir_nombre_url(
                nombre
            )

            url = URL_TIOANIME + nombre_url

            print(
                f"Anime: {nombre}"
            )

            print(
                f"Slug: {nombre_url}"
            )

            print(
                f"URL: {url}"
            )
            
            resultado = obtener_ultimo_episodio(
                driver,
                url
            )

            if resultado:

                print(
                        f"🎬 Último capítulo: "
                        f"{resultado['episodio']}"
                )

    finally:

        driver.quit()


if __name__ == "__main__":
    prueba()

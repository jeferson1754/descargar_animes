# pruebas_tioanime.py
import re
import unicodedata
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

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


def prueba(url_anime, max_intentos=3):

    print("=" * 60)
    print("PRUEBA DE BÚSQUEDA EN TIOANIME")
    print("=" * 60)

    if not url_anime:
           print("❌ URL del anime vacía.")
           return None
   
    print(
        f"📺 Consultando episodios: {url_anime}"
    )

    respuesta = None

    # --------------------------------------------------
    # Conexión con reintentos
    # --------------------------------------------------

    for intento in range(1, max_intentos + 1):

        try:

            respuesta = requests.get(
                url_anime,
                timeout=15
            )

            respuesta.raise_for_status()

            break

        except requests.exceptions.RequestException as e:

            print(
                f"⚠️ Error consultando episodios "
                f"(intento {intento}/{max_intentos}): {e}"
            )

            if intento < max_intentos:
                print("🔄 Reintentando...")
            else:
                print(
                    "❌ No se pudo acceder a la página."
                )
                return None

    # --------------------------------------------------
    # Procesar HTML
    # --------------------------------------------------

    try:

        soup = BeautifulSoup(
            respuesta.text,
            "html.parser"
        )

        episodios = []

        # Los episodios están dentro de:
        # <a class="fa-play-circle ...">

        elementos = soup.select(
            "a.fa-play-circle"
        )

        for elemento in elementos:

            texto = elemento.get_text(
                " ",
                strip=True
            )

            match = re.search(
                r"Episodio\s+(\d+)",
                texto,
                re.IGNORECASE
            )

            if not match:
                continue

            numero = int(
                match.group(1)
            )

            href = elemento.get(
                "href"
            )

            if not href:
                continue

            enlace = urljoin(
                url_anime,
                href
            )

            episodios.append({
                "episodio": numero,
                "url": enlace
            })

            print(
                f"🎬 Episodio {numero}: {enlace}"
            )

        # --------------------------------------------------
        # Comprobar resultados
        # --------------------------------------------------

        if not episodios:

            print(
                "❌ No se encontraron episodios."
            )

            return None

        # --------------------------------------------------
        # Obtener el mayor episodio
        # --------------------------------------------------

        ultimo = max(
            episodios,
            key=lambda x: x["episodio"]
        )

        print(
            f"✅ Último episodio encontrado: "
            f"{ultimo['episodio']}"
        )

        print(
            f"🔗 URL: {ultimo['url']}"
        )

        return ultimo

    except Exception as e:

        print(
            f"❌ Error procesando episodios: {e}"
        )

        return None


if __name__ == "__main__":
    
    
    animes = [
        {
            "nombre": "Yomi no Tsugai",
            "episodio_actual": 18,
            "episodios_totales": 24,
            "pendientes": 1,
            "episodio_buscado": 19
        },
    ]
    
    anime = animes[0]
    
    nombre_url = convertir_nombre_url(
        anime["nombre"]
    )

    url_busqueda = URL_TIOANIME + nombre_url


    
    prueba(url_busqueda)

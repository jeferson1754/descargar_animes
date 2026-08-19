# animes/episodios.py

import re


def extraer_numero_episodio(nombre):
    """
    Extrae el número de episodio desde un nombre.

    Ejemplos:
        'Tefuda ga Oome no Victoria 7' -> 7
        'Anime X - 12' -> 12
        'Anime X episodio 5' -> 5

    Retorna:
        int -> número del episodio
        None -> si no se encuentra
    """

    if not nombre:
        return None

    patrones = [
        r'[Ee]pisodio[\s._-]*(\d+)',
        r'[Ee]pisode[\s._-]*(\d+)',
        r'[\s._-]+(\d+)$'
    ]

    for patron in patrones:

        resultado = re.search(
            patron,
            nombre.strip()
        )

        if resultado:
            return int(resultado.group(1))

    return None


def obtener_episodio_buscado(nombre):
    """
    Obtiene el episodio que estamos buscando.
    """

    return extraer_numero_episodio(nombre)


def comparar_episodios(episodio_encontrado, episodio_buscado):
    """
    Compara el episodio encontrado con el episodio buscado.

    Retorna:
        True  -> es el episodio buscado
        False -> no corresponde
    """

    if episodio_encontrado is None:
        return False

    if episodio_buscado is None:
        return False

    return episodio_encontrado == episodio_buscado


def obtener_ultimo_episodio(episodios):
    """
    Recibe una lista de números de episodios
    y devuelve el último.

    Ejemplo:
        [1, 2, 3, 4, 5] -> 5
    """

    if not episodios:
        return None

    episodios_validos = [
        episodio
        for episodio in episodios
        if isinstance(episodio, int)
    ]

    if not episodios_validos:
        return None

    return max(episodios_validos)


def verificar_si_episodio_salio(
    episodios_disponibles,
    episodio_buscado
):
    """
    Determina si el episodio buscado
    ya está disponible.

    Retorna:
        True  -> disponible
        False -> todavía no disponible
    """

    if episodio_buscado is None:
        return False

    return episodio_buscado in episodios_disponibles

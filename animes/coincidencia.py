# animes/coincidencia.py
"""
Validación ESTRICTA de que un resultado de una fuente corresponde al anime,
temporada y episodio que se buscaban.

Reemplaza las comparaciones con difflib (cutoff 0.6/0.7) de las fuentes, que
confundían "Ao no Hako" con "Ao no Hashi" o mezclaban temporadas.

Uso:
    from animes.coincidencia import nombre_coincide, validar_url_perfil
    from animes.coincidencia import validar_coincidencia_anime
"""
import re
import logging
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse, unquote

# Validación de coincidencia anime/temporada/episodio
UMBRAL_COBERTURA_NOMBRE = 0.75   # solo aplica a nombres de más de 3 palabras
UMBRAL_SIMILITUD_TOKEN = 0.85    # similitud mínima para considerar "igual" una palabra
MAX_TOKENS_EXTRA = 2             # palabras de más permitidas en el slug (None = sin límite)

# Si una fuente usa otro nombre para un anime, agrégalo aquí.
# Ejemplo: {"ao no hako": ["blue box"]}
ALIAS_ANIME = {}

PALABRAS_IGNORADAS = {
    "the", "de", "la", "el", "los", "las", "no", "wa", "ni", "to", "ga", "wo",
    "na", "a", "of", "and", "y", "season", "temporada", "tv", "sub", "espanol",
    "latino", "castellano", "online", "ver", "anime", "capitulo", "episodio",
    "episode", "hd", "gratis", "descargar", "descarga", "mega", "mediafire",
    "completo", "subtitulado", "audio", "japones",
}

# Si el resultado trae alguna de estas palabras y lo buscado no, es otra cosa
MARCADORES_VARIANTE = {
    "movie", "pelicula", "ova", "oad", "special", "especial", "recap", "resumen",
}

# Campos del dict "video" que se usan como evidencia (NO se usa "nombre" porque
# es el nombre buscado, no el encontrado).
CLAVES_URL_VIDEO = ("enlace", "url", "url_episodio", "pagina")
CLAVES_TITULO_VIDEO = ("titulo", "title", "titulo_encontrado", "nombre_encontrado", "nombre_fuente")


# ==========================================
# MEJORA 1: VALIDACIÓN DE COINCIDENCIA (ANIME + TEMPORADA + EPISODIO)
# ==========================================
#
# El buscador a veces devuelve el capítulo "correcto" pero de OTRO anime con
# nombre parecido (Ao no Hako / Ao no Hashi) o de otra temporada. Estas
# funciones revisan la URL de la página del episodio (y los títulos si el
# buscador los entrega) ANTES de aceptar el resultado.

_HOSTS_ARCHIVOS = (
    "mega.nz", "mega.co.nz", "mixdrop", "miixdrop", "mxdrop", "mp4upload",
    "mediafire", "gofile", "streamtape", "dood", "voe.sx",
)


def _es_url_de_servidor_archivos(url):
    """True si la URL apunta a un servidor de archivos (no a la ficha de un anime)."""
    host = (urlparse(url or "").netloc or "").lower()
    return any(h in host for h in _HOSTS_ARCHIVOS)



def normalizar_texto(texto):
    """Minúsculas, sin tildes y solo letras/números separados por espacios."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def extraer_slug_y_episodio(url):
    """
    Devuelve (slug, episodio) a partir de la URL de una página de episodio.

    Soporta, por ejemplo:
        https://jkanime.net/ao-no-hako/10/         -> ("ao-no-hako", 10)
        https://tioanime.com/ver/ao-no-hako-10     -> ("ao-no-hako", 10)
    Si es la ficha del anime (/anime/...), no se interpreta ningún episodio.
    """
    if not url:
        return None, None

    path = unquote(urlparse(url).path).strip("/")
    segmentos = [s for s in path.split("/") if s]
    if not segmentos:
        return None, None

    # Ficha de la serie: el número final es parte del nombre, no un episodio
    if segmentos[0].lower() in {"anime", "serie", "series", "directorio"}:
        return segmentos[-1], None

    # Patrón /nombre-anime/10/
    if len(segmentos) >= 2 and segmentos[-1].isdigit():
        return segmentos[-2], int(segmentos[-1])

    # Patrón /ver/nombre-anime-10
    ultimo = segmentos[-1]
    m = re.match(
        r"^(.*?)[-_](?:episodio[-_]|capitulo[-_]|ep[-_])?(\d+)$", ultimo)
    if m:
        return m.group(1), int(m.group(2))

    return ultimo, None


def extraer_episodio_de_texto(texto_normalizado):
    """Busca 'episodio 10', 'capitulo 10', 'ep 10'... y lo quita del texto."""
    m = re.search(
        r"\b(?:episodio|capitulo|episode|ep|cap)\s*(\d+)\b", texto_normalizado)
    if not m:
        return None, texto_normalizado
    texto = (texto_normalizado[:m.start()] + " " +
             texto_normalizado[m.end():]).strip()
    return int(m.group(1)), texto


_PATRONES_TEMPORADA = [
    r"\b(\d+)(?:st|nd|rd|th) season\b",
    r"\bseason (\d+)\b",
    r"\btemporada (\d+)\b",
    r"\bs(\d{1,2})\b",
]
_PATRONES_PARTE = [
    r"\bpart (\d+)\b",
    r"\bparte (\d+)\b",
    r"\bcour (\d+)\b",
]
_ROMANOS = {"ii": 2, "iii": 3, "iv": 4}


def extraer_temporada_y_parte(texto):
    """
    Devuelve (temporada, parte, texto_sin_marcadores).
    Si no hay marcas, se asume temporada 1 / parte 1.
    """
    temporada = None
    parte = None

    for patron in _PATRONES_TEMPORADA:
        m = re.search(patron, texto)
        if m:
            temporada = int(m.group(1))
            texto = texto.replace(m.group(0), " ")
            break

    for patron in _PATRONES_PARTE:
        m = re.search(patron, texto)
        if m:
            parte = int(m.group(1))
            texto = texto.replace(m.group(0), " ")
            break

    texto = re.sub(r"\s+", " ", texto).strip()

    if temporada is None:
        m = re.search(r"\b(ii|iii|iv)$", texto)
        if m and len(texto.split()) > 1:
            temporada = _ROMANOS[m.group(1)]
            texto = texto[:m.start()].strip()

    if temporada is None:
        m = re.search(r"\b([2-9])$", texto)
        if m and len(texto.split()) > 1:
            temporada = int(m.group(1))
            texto = texto[:m.start()].strip()

    return temporada or 1, parte or 1, texto


def tokens_significativos(texto):
    return [t for t in texto.split() if t not in PALABRAS_IGNORADAS]


def _token_coincide(token, candidatos):
    if token in candidatos:
        return True
    # Palabras cortas (ao, kun...) solo valen si son idénticas
    if len(token) < 4 or token.isdigit():
        return False
    return any(
        SequenceMatcher(None, token, c).ratio() >= UMBRAL_SIMILITUD_TOKEN
        for c in candidatos
        if not c.isdigit()
    )


def _comparar_nombre(nombre_esperado, tokens_candidato, temporada_c, parte_c, es_slug):
    """Compara un nombre esperado contra el texto candidato. -> (ok, motivo)"""
    norm = normalizar_texto(nombre_esperado)
    temporada_e, parte_e, norm_limpio = extraer_temporada_y_parte(norm)
    esperados = tokens_significativos(norm_limpio)
    candidatos = tokens_significativos(" ".join(tokens_candidato))

    if not esperados:
        return True, "sin palabras comparables"

    if temporada_e != temporada_c:
        return False, f"temporada {temporada_c} ≠ temporada esperada {temporada_e}"

    if parte_e != parte_c:
        return False, f"parte {parte_c} ≠ parte esperada {parte_e}"

    variantes = (MARCADORES_VARIANTE & set(candidatos)) - set(esperados)
    if variantes:
        return False, f"parece otra versión ({', '.join(sorted(variantes))})"

    set_cand = set(candidatos)
    coinciden = sum(1 for t in esperados if _token_coincide(t, set_cand))
    cobertura = coinciden / len(esperados)
    umbral = 1.0 if len(esperados) <= 3 else UMBRAL_COBERTURA_NOMBRE

    # "Re:Zero" -> "re zero" vs "rezero": comparar también pegando las palabras
    if "".join(esperados) in "".join(candidatos):
        cobertura = 1.0

    if cobertura < umbral:
        faltan = [t for t in esperados if not _token_coincide(t, set_cand)]
        return False, f"nombre distinto (no aparece: {', '.join(faltan)})"

    if es_slug and MAX_TOKENS_EXTRA is not None:
        extras = [t for t in candidatos if not _token_coincide(t, set(esperados))]
        if len(extras) > MAX_TOKENS_EXTRA:
            return False, f"palabras de más en el resultado ({', '.join(extras)})"

    return True, "ok"


def _recopilar_evidencias(video):
    """Lista de (origen, texto_normalizado, episodio_detectado, es_slug)."""
    evidencias = []

    for clave in CLAVES_URL_VIDEO:
        url = video.get(clave)
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        # Si es un enlace directo a un servidor de archivos, no sirve de evidencia
        if _es_url_de_servidor_archivos(url):
            continue
        slug, episodio = extraer_slug_y_episodio(url)
        texto = normalizar_texto(slug)
        if texto:
            evidencias.append((f"url[{clave}]", texto, episodio, True))

    for clave in CLAVES_TITULO_VIDEO:
        titulo = video.get(clave)
        if not isinstance(titulo, str) or not titulo.strip():
            continue
        episodio, texto = extraer_episodio_de_texto(normalizar_texto(titulo))
        if texto:
            evidencias.append((f"titulo[{clave}]", texto, episodio, False))

    return evidencias


def _coincide_texto(nombres, texto, episodio, es_slug):
    """
    Compara un texto ya normalizado (sin 'episodio N') contra los nombres esperados.

    Los portales suelen escribir el título con el episodio al final y sin la
    palabra "episodio" ("Tensei Goblin dakedo Shitsumon Aru? 6"). Ese número NO
    es una temporada, así que si coincide con el episodio buscado se prueba
    también SIN él. Devuelve (ok, motivo).
    """
    variantes = [texto]
    ep = str(episodio).strip() if episodio is not None else ""
    if ep.isdigit():
        m = re.search(rf"\s{re.escape(ep)}$", texto)
        if m:
            variantes.append(texto[:m.start()].strip())

    motivo = "sin texto que comparar"
    for variante in variantes:
        if not variante:
            continue
        temporada_c, parte_c, texto_limpio = extraer_temporada_y_parte(variante)
        for nombre in nombres:
            ok, motivo = _comparar_nombre(
                nombre, texto_limpio.split(), temporada_c, parte_c, es_slug
            )
            if ok:
                return True, "ok"

    return False, motivo


def validar_coincidencia_anime(video, nombre_esperado, episodio_esperado):
    """
    Comprueba que el resultado de una fuente corresponda al anime, la
    temporada y el episodio que se buscaban.

    Devuelve (True/False, motivo). Si el video no trae datos suficientes
    para comparar, no lo rechaza (devuelve True) pero lo deja en el log.
    """
    evidencias = _recopilar_evidencias(video)

    if not evidencias:
        logging.warning(
            "⚠️ No hay URL ni título del resultado para validar la coincidencia "
            f"de '{nombre_esperado}'. Se acepta sin verificar."
        )
        return True, "sin datos para validar"

    nombres = [nombre_esperado] + \
        ALIAS_ANIME.get(normalizar_texto(nombre_esperado), [])
    ep_esperado = (
        int(episodio_esperado)
        if str(episodio_esperado).strip().isdigit()
        else None
    )

    for origen, texto, ep_detectado, es_slug in evidencias:

        if (
            ep_esperado is not None
            and ep_detectado is not None
            and ep_detectado != ep_esperado
        ):
            return False, f"{origen}: episodio {ep_detectado} ≠ {ep_esperado}"

        # Para las URL el episodio ya se extrajo del slug; para los títulos se
        # prueba también sin el número final si coincide con el episodio buscado.
        ok, motivo = _coincide_texto(
            nombres, texto, None if es_slug else ep_esperado, es_slug)
        if not ok:
            return False, f"{origen}: {motivo}"

    return True, "ok"




# ==========================================
# API SIMPLE PARA LAS FUENTES (jkanime, animeflv, monoschinos, tioanime)
# ==========================================

def nombre_coincide(nombre_buscado, titulo_encontrado, episodio=None, es_slug=False):
    """
    Reemplazo estricto de difflib.get_close_matches(...) en las fuentes.

    True solo si 'titulo_encontrado' es el MISMO anime (misma temporada/parte,
    sin palabras clave distintivas faltantes) que 'nombre_buscado'.

    - Ignora 'Episodio N' dentro del título.
    - Si se pasa 'episodio' y el título termina con ese número suelto
      ("Ao no Hako 9"), se prueba también sin él para no confundirlo con una
      temporada.
    """
    texto = normalizar_texto(titulo_encontrado)
    if not texto:
        return False

    _, texto = extraer_episodio_de_texto(texto)

    nombres = [nombre_buscado] + \
        ALIAS_ANIME.get(normalizar_texto(nombre_buscado), [])

    ok, motivo = _coincide_texto(nombres, texto, episodio, es_slug)
    if ok:
        return True

    logging.info(f"🔎 '{titulo_encontrado}' ≠ '{nombre_buscado}': {motivo}")
    return False


def validar_url_perfil(url_perfil, nombre_buscado):
    """
    Verifica que la URL de la ficha del anime (primer resultado del buscador de
    la web) sea realmente el anime buscado. Se usa en el 'perfil' de las
    fuentes, que antes aceptaban el primer resultado sin comprobar nada.

    No interpreta ningún número final como episodio.
    Si no hay texto que comparar, no rechaza.
    """
    if not url_perfil:
        return False

    path = unquote(urlparse(url_perfil).path).strip("/")
    segmentos = [x for x in path.split("/") if x]

    # Último segmento que contenga letras (evita IDs puramente numéricos)
    slug = next((x for x in reversed(segmentos) if re.search(r"[a-zA-Z]", x)), None)
    if not slug:
        return True

    return nombre_coincide(nombre_buscado, slug, es_slug=True)
from fuentes.tioanime import buscar_videos_tioanime
from fuentes.jkanime import buscar_videos_jkanime
#from fuentes.animeflv import buscar_videos_animeflv


# ============================================================
# CARPETAS
# ============================================================

DOWNLOAD_DIR = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"

DOWNLOAD_DIR_2 = r"D:\Xampp\htdocs\descargar_animes\Descargas"

SERVIDOR = "https://inventarioncc.infinityfreeapp.com/"
# SERVIDOR = "http://localhost/"

# ============================================================
# FUENTES DE ANIME
# ============================================================

FUENTES_ANIME = [
    {
        "nombre": "TioAnime",
        "url": "https://tioanime.com/",
        "activa": True,
        "buscar": buscar_videos_tioanime
    },
    {
        "nombre": "Jkanime",
        "url": "https://jkanime.net/",
        "activa": True,
        "buscar": buscar_videos_jkanime
    }
]


# ============================================================
# DESCARGAS
# ============================================================

MAX_INTENTOS = 3

TIMEOUT_DESCARGA = 900

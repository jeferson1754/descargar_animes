from fuentes.tioanime import buscar_videos_tioanime


# ============================================================
# CARPETAS
# ============================================================

DOWNLOAD_DIR = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"

DOWNLOAD_DIR_2 = r"D:\Xampp\htdocs\descargar_animes\Descargas"


# ============================================================
# FUENTES DE ANIME
# ============================================================

FUENTES_ANIME = [
    {
        "nombre": "TioAnime",
        "url": "https://tioanime.com/",
        "activa": True,
        "buscar": buscar_videos_tioanime
    }
]


# ============================================================
# DESCARGAS
# ============================================================

MAX_INTENTOS = 3

TIMEOUT_DESCARGA = 900

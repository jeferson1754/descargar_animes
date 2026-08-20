from fuentes.tioanime import buscar_pagina_principal


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
        "buscar": buscar_pagina_principal
    }
]


# ============================================================
# DESCARGAS
# ============================================================

MAX_INTENTOS = 3

TIMEOUT_DESCARGA = 900

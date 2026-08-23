# pruebas_tioanime.py
import re
import unicodedata
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


import sys
import os

# Agrega la raíz del proyecto al path de Python para evitar errores de importación
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utilidades.navegador import configurar_navegador
from config import DOWNLOAD_DIR_2
from download.descargar import flujo_descarga_animes
from base_excel import obtener_conexion_google_sheets, guardar_resultados_en_sheets




if __name__ == "__main__":
# 1. Convertirlo en una LISTA de diccionarios (usando corchetes [])
    animes = [
        {
            "nombre": "Tenmaku no Jaadugar Episodio 8",
            "link_descarga": "https://mega.nz/#!cXFwzSJC!JkMylO_o0BJKIgEapPUCx5j1eBddAVJuWtQWiB4feuo"
        },
        {
            "nombre": "Tenmaku no Jaadugar Episodio 9",
            "enlace": "https://mega.nz/#!sTkkiRzD!IfMXgbeOIIiBEG1DR7xOuaamBqBrrLo_XKl1JDlIQQ4"
        }
    ]

    flujo_descarga_animes("animes_no_descargados.txt", DOWNLOAD_DIR_2)
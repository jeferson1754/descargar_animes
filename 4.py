import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import difflib
import requests
import time
import re
import os
import shutil

from animes.buscador import extraer_nombres_anime
from utilidades.archivos import guardar_resultados_animes_txt, guardar_archivos_descargados, guardar_animes_no_descargados, leer_nombres_animes_a_descargar, mover_videos_y_limpiar_carpetas, eliminar_txt
from animes.comparador import obtener_archivos_descargados, comparar_descargas
from download.descargar import flujo_descarga_animes


def main(download_dir, archivo_animes, archivo_resultado_descargados, archivo_resultado_no_descargados):
    """
    Función principal que gestiona la verificación de los animes a descargar.

    Args:
        download_dir (str): Directorio de descargas.
        archivo_animes (str): Archivo de animes a descargar.
        archivo_resultado_descargados (str): Archivo donde se guardarán los archivos descargados.
        archivo_resultado_no_descargados (str): Archivo donde se guardarán los animes no descargados.
    """

    mover_videos_y_limpiar_carpetas(download_dir, download_dir)

    # Obtener los archivos descargados
    archivos_descargados = obtener_archivos_descargados(download_dir)

    if not archivos_descargados:
        print("No se encontraron archivos en el directorio de descargas.")
        # Asegurar que el archivo de animes no descargados se crea
        animes_a_descargar = leer_nombres_animes_a_descargar(archivo_animes)

        if not animes_a_descargar:
            print("No se encontraron animes para descargar.")
            return

        # Todos los animes en la lista de descargas se consideran no descargados
        guardar_animes_no_descargados(
            animes_a_descargar, archivo_resultado_no_descargados)
        print(f"Se ha creado el archivo {
              archivo_resultado_no_descargados} con todos los animes.")
        return

    # Guardar los archivos descargados en un archivo .txt
    guardar_archivos_descargados(
        archivos_descargados, archivo_resultado_descargados)

    # Leer los nombres de los animes a descargar
    animes_a_descargar = leer_nombres_animes_a_descargar(archivo_animes)

    if not animes_a_descargar:
        print("No se encontraron animes para descargar.")
        return

    # Comparar los animes a descargar con los archivos ya descargados
    animes_no_descargados = comparar_descargas(
        animes_a_descargar, archivos_descargados)

    if not animes_no_descargados:
        print("Todos los animes ya han sido descargados.")
    else:
        print("Animes que no han sido descargados:")
        for anime in animes_no_descargados:
            print(f"- {anime}")

    # Guardar los animes no descargados en un archivo .txt
    guardar_animes_no_descargados(
        animes_no_descargados, archivo_resultado_no_descargados)


def menu_dias():
    dias = {
        "1": "Lunes",
        "2": "Martes",
        "3": "Miércoles",
        "4": "Jueves",
        "5": "Viernes",
        "6": "Sábado",
        "7": "Domingo",
        "0": "Volver al menú principal"
    }

    while True:
        print("\n=== Seleccione un día ===")
        for clave, dia in dias.items():
            print(f"{clave}. {dia}")

        opcion_dia = input("Seleccione un día: ")

        if opcion_dia in dias:
            if opcion_dia == "0":
                return None  # Volver al menú principal
            else:
                dia_seleccionado = dias[opcion_dia]
                # Construir URL con el día seleccionado
                url = f"https://inventarioncc.infinityfreeapp.com/Anime/Emision/?dias={dia_seleccionado}&enviar2=&accion=Filtro"
                return url
        else:
            print("❌ Opción inválida. Intente de nuevo.")


def menu_principal(download_dir):
    while True:
        print("\n=== MENÚ DE OPCIONES ===")
        print("1. Descargar animes de hoy")
        print("2. Descargar animes pendientes")
        print("3. Seleccionar un día")
        print("4. Sacar videos de carpetas de descargas")

        opcion = input("Seleccione una opción: ")

        if opcion == "1":
            url = "https://inventarioncc.infinityfreeapp.com/Anime/Emision/?enviar=&accion=HOY"
            return url
        elif opcion == "2":
            url = "https://inventarioncc.infinityfreeapp.com/Anime/Emision/?faltantes=&accion=HOY"
            return url
        elif opcion == "3":
            url = menu_dias()
            if url:
                return url
        elif opcion == "4":
            mover_videos_y_limpiar_carpetas(download_dir, download_dir)
        else:
            print("❌ Opción inválida. Intente de nuevo.")


def menu():

    # Definir ambas rutas
    ruta_1 = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"
    ruta_2 = r"D:\Xampp\htdocs\descargar_animes\Descargas"

    # Verificar si la primera ruta existe; si no, usar la segunda
    if os.path.exists(ruta_1):
        download_dir = ruta_1
        print(f"📁 Usando ruta principal: {download_dir}")
    else:
        download_dir = ruta_2
        print(
            f"⚠️ La ruta principal no existe. Usando ruta alternativa: {download_dir}")

    # URL de la página a analizar
    url = menu_principal(download_dir)

    if url is None or url == "":
        print("No se seleccionó ninguna opción válida. Volviendo al menú principal...")
        menu()

    # Extraer y mostrar los nombres de los animes
    nombres_anime = extraer_nombres_anime(url, download_dir)

    # Guardar los nombres en un archivo .txt
    guardar_resultados_animes_txt(nombres_anime, "resultados_anime.txt")

    # Mostrar conteo y los nombres en la consola
    conteo_anime = len(nombres_anime)

    # Ruta de la carpeta de descargas y archivo de animes
    archivo_animes = "resultados_anime.txt"
    archivo_resultado_descargados = "archivos_descargados.txt"
    archivo_resultado_no_descargados = "animes_no_descargados.txt"

    print(f"Cantidad de animes extraídos: {conteo_anime}")
    for nombre in nombres_anime:
        print(nombre)

    print(f"Datos guardados en 'resultados_anime.txt'")

    # Ejecutar la función principal
    main(download_dir, archivo_animes, archivo_resultado_descargados,
         archivo_resultado_no_descargados)

    # Ejecutar función principal solo si hay animes por descargar
    if not os.path.exists(archivo_resultado_no_descargados) or os.path.getsize(archivo_resultado_no_descargados) == 0:
        print("No se ejecuta la funcion buscar videos de anime")
    else:
        continuar_descarga = flujo_descarga_animes(
            archivo_resultado_no_descargados, download_dir)

        if continuar_descarga is False:
            eliminar_txt()
            print("\nVolviendo al menú principal...")
            return menu()

    eliminar_txt()


if __name__ == "__main__":
    menu()

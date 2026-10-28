import subprocess
import os
from dotenv import load_dotenv
import glob
from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError
import time
import json
import shutil

load_dotenv()

CARPETA_DESCARGAS = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"
CARPETA_TEMPORAL = r"C:\Users\jvargas\Phyton\Descargar_Animes\recorte\frames_temp"
API_KEY_GEMINI = os.environ.get("GEMINI_API_KEY")


def renombrar_fotogramas_con_tiempo(output_dir):
    """
    Renombra los fotogramas extraídos asignando el minuto y segundo real
    según la regla de muestreo (cada 20s los primeros 240s; cada 60s después).
    """
    archivos = sorted([f for f in os.listdir(
        output_dir) if f.endswith(".jpg")])

    segundos_acumulados = 0

    for idx, nombre_archivo in enumerate(archivos):
        # Calcular minutos y segundos para el nombre
        minutos = segundos_acumulados // 60
        segundos = segundos_acumulados % 60

        nuevo_nombre = f"frame_{minutos:02d}m{segundos:02d}s.jpg"

        ruta_antigua = os.path.join(output_dir, nombre_archivo)
        ruta_nueva = os.path.join(output_dir, nuevo_nombre)

        # Renombrar archivo
        os.rename(ruta_antigua, ruta_nueva)

        # Incrementar tiempo para el siguiente fotograma
        if segundos_acumulados < 240:
            segundos_acumulados += 20
        else:
            segundos_acumulados += 60

    print(
        f"¡Fotogramas renombrados correctamente con sus marcas de tiempo reales en '{output_dir}'!")


def extraer_fotogramas_minuto(video_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    else:
        # Limpiar imágenes anteriores para evitar duplicados
        for f in os.listdir(output_dir):
            if f.endswith(".jpg"):
                os.remove(os.path.join(output_dir, f))

    # Obtenemos la ruta absoluta de la carpeta donde está este script (recorte)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Apuntamos directamente al ffmpeg.exe ubicado en la misma carpeta
    ffmpeg_executable = os.path.join(script_dir, "ffmpeg.exe")

    # Filtro: Cada 20s los primeros 4 min (t < 240) y cada 60s después
    filter_expr = (
        "select='if(lt(t,240), isnan(prev_selected_t)+gte(t-prev_selected_t,20), "
        "isnan(prev_selected_t)+gte(t-prev_selected_t,60))'"
    )

    command = [
        ffmpeg_executable, "-y",
        "-i", video_path,
        "-vf", filter_expr,
        "-vsync", "vfr",
        os.path.join(output_dir, "temp_%03d.jpg")
    ]

    # Ejecutamos el comando
    resultado = subprocess.run(command, capture_output=True, text=True)

    if resultado.returncode == 0:
        print("Fotogramas base extraídos. Aplicando timestamps reales...")
        renombrar_fotogramas_con_tiempo(output_dir)
    else:
        print(f"Hubo un error de FFmpeg: {resultado.stderr}")


def limpiar_carpeta_temporal(output_dir):
    """
    Elimina por completo la carpeta temporal de fotogramas al finalizar.
    """
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
        print("🧹 Carpeta temporal de fotogramas limpiada y eliminada.")


def convertir_a_segundos(tiempo):
    """
    Convierte entradas en minutos (int/float), segundos (int/float)
    o cadenas formato "MM:SS" / "SS" a un total flotante en segundos.
    """
    if isinstance(tiempo, (int, float)):
        return float(tiempo) * 60 if tiempo < 100 else float(tiempo)
    elif isinstance(tiempo, str):
        partes = tiempo.strip().split(':')
        if len(partes) == 2:  # Formato MM:SS
            return float(partes[0]) * 60 + float(partes[1])
        elif len(partes) == 3:  # Formato HH:MM:SS
            return float(partes[0]) * 3600 + float(partes[1]) * 60 + float(partes[2])
        return float(tiempo)
    return float(tiempo)


def procesar_video_acelerado(video_path, output_path, op_start, op_end, ed_start, ed_end, velocidad=3.0):
    """
    Mantiene OP y ED a 1.0x y acelera las demás partes a 3.0x.
    Incluye un manejo de errores robusto y retorna True/False según el resultado.
    """
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ffmpeg_executable = os.path.join(script_dir, "ffmpeg.exe")

        if not os.path.exists(ffmpeg_executable):
            print(
                f"❌ Error crítico: No se encuentra 'ffmpeg.exe' en {script_dir}")
            return False

        # Convertimos los 4 puntos de corte a segundos exactos
        op_start_sec = convertir_a_segundos(op_start)
        op_end_sec = convertir_a_segundos(op_end)
        ed_start_sec = convertir_a_segundos(ed_start)
        ed_end_sec = convertir_a_segundos(ed_end)

        # Validación lógica básica de tiempos
        if not (op_start_sec <= op_end_sec <= ed_start_sec <= ed_end_sec):
            print(
                f"⚠️ Advertencia: Los tiempos de corte no son secuenciales lógicos para {os.path.basename(video_path)}.")

        # Configuración de aceleración para audio (atempo máx 2.0 por filtro)
        if velocidad == 3.0:
            filtro_audio = "atempo=2.0,atempo=1.5"
        elif velocidad > 2.0:
            filtro_audio = f"atempo=2.0,atempo={velocidad / 2.0:.2f}"
        else:
            filtro_audio = f"atempo={velocidad}"

        factor_v = 1.0 / velocidad

        # Construcción de los 5 tramos en FFmpeg
        filter_complex = (
            f"[0:v]trim=start=0:end={op_start_sec:.2f},setpts={factor_v:.6f}*(PTS-STARTPTS)[v0];"
            f"[0:a]atrim=start=0:end={op_start_sec:.2f},asetpts=PTS-STARTPTS,{filtro_audio}[a0];"

            f"[0:v]trim=start={op_start_sec:.2f}:end={op_end_sec:.2f},setpts=PTS-STARTPTS[v1];"
            f"[0:a]atrim=start={op_start_sec:.2f}:end={op_end_sec:.2f},asetpts=PTS-STARTPTS[a1];"

            f"[0:v]trim=start={op_end_sec:.2f}:end={ed_start_sec:.2f},setpts={factor_v:.6f}*(PTS-STARTPTS)[v2];"
            f"[0:a]atrim=start={op_end_sec:.2f}:end={ed_start_sec:.2f},asetpts=PTS-STARTPTS,{filtro_audio}[a2];"

            f"[0:v]trim=start={ed_start_sec:.2f}:end={ed_end_sec:.2f},setpts=PTS-STARTPTS[v3];"
            f"[0:a]atrim=start={ed_start_sec:.2f}:end={ed_end_sec:.2f},asetpts=PTS-STARTPTS[a3];"

            f"[0:v]trim=start={ed_end_sec:.2f},setpts={factor_v:.6f}*(PTS-STARTPTS)[v4];"
            f"[0:a]atrim=start={ed_end_sec:.2f},asetpts=PTS-STARTPTS,{filtro_audio}[a4];"

            f"[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4]concat=n=5:v=1:a=1[v][a]"
        )

        command = [
            ffmpeg_executable, "-y",
            "-threads", "4",  # Limita los hilos de procesamiento para proteger tu CPU y RAM
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            output_path
        ]

        print(
            f"Procesando video con aceleración a {velocidad}x respetando OP y ED...")

        # Ejecutamos con un timeout de seguridad por si se queda colgado (ej. 15 minutos por video)
        resultado = subprocess.run(
            command, capture_output=True, text=True, timeout=900)

        if resultado.returncode == 0:
            print(f"¡Éxito! Video procesado guardado en: {output_path}")
            return True
        else:
            print(
                f"❌ Error de FFmpeg al procesar el video: {resultado.stderr}")
            # Si el archivo de salida parcial se creó corrupto, lo borramos
            if os.path.exists(output_path):
                os.remove(output_path)
            return False

    except subprocess.TimeoutExpired:
        print("❌ Error: El proceso de FFmpeg tardó demasiado tiempo y fue cancelado.")
        return False
    except Exception as e:
        print(f"❌ Error inesperado en procesar_video_acelerado: {e}")
        return False


def renombrar_video_original(video_path):
    """
    Renombra el video original agregando 'ORIGINAL_' al inicio
    para que la barrida de descargas no lo vuelva a procesar.
    """
    directorio, nombre_archivo = os.path.split(video_path)
    nuevo_nombre = f"ORIGINAL_{nombre_archivo}"
    nueva_ruta = os.path.join(directorio, nuevo_nombre)

    os.rename(video_path, nueva_ruta)
    print(f"🏷️ Video original renombrado a: {nuevo_nombre}")
    return nueva_ruta


def validar_estructura_tiempos(datos):
    """
    Valida que el diccionario devuelto por la IA tenga las claves necesarias
    y valores lógicos en SEGUNDOS para un episodio de anime.
    """
    claves_requeridas = ["op_inicio", "op_fin", "ed_inicio", "ed_fin"]

    # 1. Comprobar que sea un diccionario y tenga todas las claves
    # Valores por defecto en segundos: OP de 120s (min 2) a 180s (min 3), ED de 1320s (min 22) a 1380s (min 23)
    defaults = {"op_inicio": 120.0, "op_fin": 180.0,
                "ed_inicio": 1320.0, "ed_fin": 1380.0}

    if not isinstance(datos, dict) or not all(k in datos for k in claves_requeridas):
        print("⚠️ La IA devolvió un JSON incompleto o con formato incorrecto. Aplicando valores por defecto.")
        return defaults

    try:
        # 2. Convertir a float por seguridad y validar rangos lógicos básicos (en segundos)
        op_inicio = float(datos["op_inicio"])
        op_fin = float(datos["op_fin"])
        ed_inicio = float(datos["ed_inicio"])
        ed_fin = float(datos["ed_fin"])

        # Validación de cordura en SEGUNDOS: Si el OP empieza más allá de los 10 minutos (600 segundos), corregirlo
        if op_inicio > 600.0:
            print(
                "⚠️ Advertencia: OP detectado muy tarde por la IA (> 10 minutos). Ajustando a rango estándar.")
            op_inicio, op_fin = 120.0, 180.0
        return {
            "op_inicio": op_inicio,
            "op_fin": op_fin,
            "ed_inicio": ed_inicio,
            "ed_fin": ed_fin
        }
    except (ValueError, TypeError):
        print("⚠️ Error al parsear los valores numéricos del JSON de la IA. Aplicando valores por defecto.")
        return defaults


def analizar_fotogramas_con_gemini(frames_dir, max_retros=3):
    client = genai.Client(api_key=API_KEY_GEMINI)

    image_paths = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    if not image_paths:
        print("No se encontraron fotogramas para analizar.")
        return None

    # Preparamos las imágenes una sola vez
    contents_base = []
    for path in image_paths:
        with open(path, "rb") as f:
            image_bytes = f.read()
        contents_base.append(types.Part.from_bytes(
            data=image_bytes, mime_type="image/jpeg"))
        contents_base.append(f"Archivo: {os.path.basename(path)}")

    # --- INTENTO 1: Prompt Normal ---
    prompt_normal = (
        "Eres un asistente experto en análisis de video de anime. "
        "Te entrego una secuencia cronológica de fotogramas cuyos nombres indican su marca de tiempo exacta "
        "(por ejemplo, frame_01m40s.jpg es el minuto 1 con 40 segundos). "
        "Identifica con precisión el inicio y el fin del Opening (OP) y del Ending (ED) en SEGUNDOS. "
        "Devuélveme estrictamente un JSON válido con este formato exacto y sin texto adicional: "
        '{"op_inicio": número, "op_fin": número, "ed_inicio": número, "ed_fin": número}'
    )

    contents_intento_1 = contents_base + [prompt_normal]

    print("Enviando consulta a Gemini (Intento Principal)...")
    datos_json = ejecutar_llamada_gemini(client, contents_intento_1)

    # --- VALIDACIÓN INTELIGENTE ---
    # Verificamos si los datos son válidos y si el OP está en un rango lógico (ej: menor a 600 segundos / 10 min)
    if datos_json and "op_inicio" in datos_json:
        op_inicio_val = float(datos_json["op_inicio"])

        if 0 <= op_inicio_val <= 600.0:
            # ¡Todo bien! Los datos tienen sentido
            return datos_json
        else:
            print(
                f"⚠️ Alerta: La IA detectó un OP ilógico ({op_inicio_val}s). Activando reintento con enfoque estricto...")
    else:
        print("⚠️ Alerta: No se pudo obtener un JSON válido. Activando reintento con enfoque estricto...")

    # --- INTENTO 2: Prompt Enfocado de Rescate ---
    prompt_enfocado = (
        "⚠️ CORRECCIÓN IMPORTANTE: En tu análisis anterior fallaste o diste un tiempo erróneo para el Opening. "
        "Los openings en el anime siempre ocurren estrictamente entre el **minuto 1 y el minuto 3** (de 60 a 180 segundos). "
        "Ignora cualquier otra escena y concéntrate únicamente en buscar los créditos de inicio y la canción en ese rango específico. "
        "Devuélveme estrictamente un JSON válido con este formato y sin texto adicional: "
        '{"op_inicio": número, "op_fin": número, "ed_inicio": número, "ed_fin": número}'
    )

    contents_intento_2 = contents_base + [prompt_enfocado]

    print("Enviando consulta de rescate a Gemini (Prompt enfocado 1m - 3m)...")
    datos_json_rescate = ejecutar_llamada_gemini(client, contents_intento_2)

    if datos_json_rescate and "op_inicio" in datos_json_rescate:
        print("¡Rescate exitoso con prompt enfocado!")
        return datos_json_rescate
    else:
        print("❌ El reintento enfocado también falló. Aplicando respaldo de emergencia dinámico (Minuto 1.5).")
        # Respaldo dinámico basado en la estructura real (minuto 1:30 a 3:00)
        return {"op_inicio": 90.0, "op_fin": 180.0, "ed_inicio": 1320.0, "ed_fin": 1380.0}


def ejecutar_llamada_gemini(client, contents):
    """Función auxiliar para manejar la llamada y errores de la API"""
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=contents,
        )
        texto_respuesta = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(texto_respuesta)
    except Exception as e:
        print(f"Error en llamada a Gemini: {e}")
        return None


def main():
    # El uso de '**/*.mp4' con recursive=True escanea todas las subcarpetas dentro de descargas
    patron_busqueda = os.path.join(CARPETA_DESCARGAS, "**", "*.mp4")
    videos = glob.glob(patron_busqueda, recursive=True)

    if not videos:
        print(
            "No se encontraron videos MP4 en la carpeta de descargas ni en sus subcarpetas.")
        return

    print(f"Se encontraron {len(videos)} videos para procesar en total.")

    for video_path in videos:
        nombre_archivo = os.path.basename(video_path)
        # Omite si es el video final procesado O si ya fue marcado como ORIGINAL
        if "_procesado.mp4" in nombre_archivo or nombre_archivo.startswith("ORIGINAL_"):
            continue

        print(f"\n--- Procesando: {nombre_archivo} ---")
        output_path = video_path.replace(".mp4", "_procesado.mp4")

        # 1. Extraer fotogramas
        print("1. Extrayendo fotogramas...")
        extraer_fotogramas_minuto(video_path, CARPETA_TEMPORAL)

        # 2. Consultar a Gemini
        print("2. Consultando a Gemini los tiempos de OP y ED...")
        tiempos = analizar_fotogramas_con_gemini(CARPETA_TEMPORAL)

        if not tiempos:
            print(
                "No se pudo obtener respuesta válida de la IA para este video. Saltando...")
            continue

        print(f"Tiempos detectados: {tiempos}")

        # 3. Procesar y acelerar con FFmpeg
        print("3. Aplicando recorte y aceleración x3 con FFmpeg...")
        # 3. Procesar y acelerar con FFmpeg
        exito_procesamiento = procesar_video_acelerado(
            video_path=video_path,
            output_path=output_path,
            op_start=tiempos.get("op_inicio", 0),
            op_end=tiempos.get("op_fin", 2),
            ed_start=tiempos.get("ed_inicio", 22),
            ed_end=tiempos.get("ed_fin", 23),
            velocidad=3.0
        )

        # 4. Solo si FFmpeg terminó con éxito, renombramos el original
        if exito_procesamiento:
            renombrar_video_original(video_path)
        else:
            print(
                f"⚠️ El video {os.path.basename(video_path)} no se pudo procesar. Se mantiene intacto para reintentar luego.")

        # Al terminar de procesar todos los videos en main():
        limpiar_carpeta_temporal(CARPETA_TEMPORAL)


if __name__ == "__main__":
    main()

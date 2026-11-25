#!/usr/bin/env python3
"""
anime_x3.py - Procesa episodios de anime a velocidad xN respetando OP y ED.

Estructura de salida (5 tramos):
    [ inicio -> OP ]  xN
    [     OP        ]  x1
    [ OP -> ED      ]  xN
    [     ED        ]  x1
    [ ED -> fin     ]  xN

Marcas de tiempo:
    Solo Gemini: se le envía una versión liviana del episodio y devuelve los tiempos de OP/ED.

Archivos:
    Dentro de la carpeta de cada fecha (o de donde esté el episodio) se crean dos subcarpetas:
        <carpeta>/procesados/Episodio.mp4   -> el episodio acelerado
        <carpeta>/originales/Episodio.mkv   -> el episodio original, sin cambiar de nombre

Avisos por Telegram (usa notificaciones_telegram.enviar_mensaje_telegram):
    - Cada episodio procesado: archivo, modelo de Gemini que detectó OP/ED, tiempos y duración.
    - Cada fallo: archivo y el motivo (cuota de Gemini, modelo no disponible, FFmpeg, etc.).
    - Si el script no puede iniciar (sin carpeta, sin ffmpeg, sin clave de Gemini).

Requisitos:
    pip install google-genai python-dotenv
    ffmpeg.exe junto al script (o ffmpeg en el PATH); ffprobe es opcional
    Clave de Gemini: variable GEMINI_API_KEY o archivo gemini_key.txt junto al script
    notificaciones_telegram.py con enviar_mensaje_telegram(texto)  (opcional)

Uso:
    python anime_x3.py "D:/Anime/entrada" "D:/Anime/salida"
    python anime_x3.py ENTRADA SALIDA --threads 2 --speed 3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

# Avisos por Telegram: si el módulo no existe, el script funciona igual (solo sin avisos)
try:
    from notificaciones_telegram import enviar_mensaje_telegram
except ImportError:
    enviar_mensaje_telegram = None
# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v"}

# --- Rutas por defecto: se usan si ejecutas sin argumentos (botón "Run" de VS Code) ---
DEFAULT_INPUT = os.environ.get("CARPETA_DESCARGAS")

if not DEFAULT_INPUT:
    raise ValueError("❌ Error: La variable de entorno 'CARPETA_DESCARGAS' no está configurada.")
else:
    DEFAULT_INPUT = Path(DEFAULT_INPUT)
# <carpeta del episodio>/procesados  (acelerados)
PROCESSED_DIRNAME = "procesados"
# <carpeta del episodio>/originales  (originales)
ORIGINALS_DIRNAME = "originales"
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

HORAS_EJECUCION = (15, 19)
HORA_REPROCESO_MODELO = 19
VERSION_MODELO_MINIMA = (3, 6)

MODELOS_FALLBACK = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite"
]


def _version_modelo(nombre: str | None) -> tuple[int, int] | None:
    """Extrae (mayor, menor) de un nombre de modelo Gemini (ej. 'gemini-3.6-flash' -> (3, 6))."""
    if not nombre:
        return None
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", str(nombre).lower())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0))


def _modelos_superiores(model_preferido: str, version_min_exclusiva: tuple[int, int]) -> list[str]:
    """Modelos disponibles con versión estrictamente superior a `version_min_exclusiva`."""
    candidatos = [model_preferido] + [m for m in MODELOS_FALLBACK if m != model_preferido]
    resultado = []
    for m in candidatos:
        v = _version_modelo(m)
        if v is not None and v > version_min_exclusiva:
            resultado.append(m)
    return resultado

# versiones anteriores renombraban así; se ignoran
LEGACY_PREFIX = "original_"
GEMINI_TIMEOUT_MS = 180_000        # 3 min máx. por petición a Gemini
MIN_OPED, MAX_OPED = 20.0, 240.0   # duración válida (s) de un OP/ED
OUTPUT_NAME_RE = re.compile(r"\[x\d+(?:\.\d+)?\](?:\.part)?$", re.I)
MIN_SEGMENT = 0.5                  # tramos más cortos que esto se descartan

log = logging.getLogger("anime_x3")

SCRIPT_DIR = Path(__file__).resolve().parent


def find_tool(name: str) -> str | None:
    """Busca ffmpeg/ffprobe primero junto al script (ffmpeg.exe) y luego en el PATH."""
    local = SCRIPT_DIR / (name + (".exe" if os.name == "nt" else ""))
    if local.is_file():
        return str(local)
    return shutil.which(name)


FFMPEG = find_tool("ffmpeg")
# opcional: si no existe, se usa ffmpeg para analizar
FFPROBE = find_tool("ffprobe")


# --------------------------------------------------------------------------- #
# Utilidades generales
# --------------------------------------------------------------------------- #
def load_cache(path: Path) -> dict:
    cache = {"marks": {}, "done": {}}
    if path.exists():
        try:
            cache.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            log.warning("Caché corrupta, se reinicia.")
    return cache


def save_cache(path: Path, cache: dict) -> None:
    path.write_text(json.dumps(cache, indent=2,
                    ensure_ascii=False), encoding="utf-8")


def run_low_priority(cmd: list[str]) -> subprocess.CompletedProcess:
    """Ejecuta un comando con prioridad baja para no ahogar el PC / VS Code."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    else:
        kwargs["preexec_fn"] = lambda: os.nice(10)
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def fmt_dur(seconds: float) -> str:
    """1443 -> '24:03' ; 3725 -> '1:02:05'."""
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


_aviso_sin_telegram = False


def notificar(texto: str) -> None:
    """Envía un aviso por Telegram. Nunca debe romper el procesamiento."""
    global _aviso_sin_telegram
    if enviar_mensaje_telegram is None:
        if not _aviso_sin_telegram:
            log.warning("No encuentro notificaciones_telegram.py: no se enviarán avisos.")
            _aviso_sin_telegram = True
        return
    texto = texto[:3900]                       # límite de Telegram: 4096 caracteres
    try:
        enviar_mensaje_telegram(texto)
    except Exception:
        try:                                   # reintento sin caracteres que rompen Markdown/HTML
            enviar_mensaje_telegram(re.sub(r"[_*`\[\]<>&]", " ", texto))
        except Exception as e:
            log.warning("No pude enviar el aviso a Telegram: %s", e)


# --------------------------------------------------------------------------- #
# Gemini: detección de OP/ED
# --------------------------------------------------------------------------- #
GEMINI_PROMPT = """Analiza este episodio de anime (duración total: {dur:.0f} segundos).
Devuelve SOLO un JSON con estas claves, en segundos desde el inicio del video:
{{"op_start": number|null, "op_end": number|null, "ed_start": number|null, "ed_end": number|null}}
- Opening: canción de apertura con créditos animados.
- Ending: canción de cierre / créditos finales (no incluyas el avance del próximo episodio).
- Si el episodio NO tiene opening (o no tiene ending), pon null en sus dos claves. Nunca uses 0 para indicar que no existe.
- Es normal que solo exista uno de los dos. Precisión deseada: ±1 segundo."""


def make_proxy(src: Path, dst: Path, threads: int) -> None:
    """Video diminuto (240p, 1 fps, audio mono) solo para que Gemini lo analice."""
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(src), "-vf", "scale=-2:240,fps=1", "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "32k",
        "-threads", str(threads), str(dst),
    ]
    r = run_low_priority(cmd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])


def load_gemini_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key and key.strip():
        return key.strip()
    for name in ("gemini_key.txt", "GEMINI_API_KEY.txt"):
        f = SCRIPT_DIR / name
        if f.is_file():
            k = f.read_text(encoding="utf-8").strip()
            if k:
                return k
    return None


def _motivo_corto(error: Exception) -> str:
    """Resume un error de Gemini para dejarlo en la hoja."""
    texto = str(error)
    if "429" in texto or "ResourceExhausted" in texto or "quota" in texto.lower():
        return "cuota agotada"
    if "503" in texto or "UNAVAILABLE" in texto:
        return "modelo no disponible (503)"
    if "404" in texto or "NOT_FOUND" in texto:
        return "modelo no encontrado (404)"
    if "timeout" in texto.lower() or "timed out" in texto.lower():
        return "tiempo de espera agotado"
    return texto.replace("\n", " ")[:80]


def gemini_marks(src: Path, duration: float, threads: int, model: str,
                 meta: dict | None = None,
                 modelos_permitidos: list[str] | None = None) -> dict:
    """
    Devuelve {"op": [...]|None, "ed": [...]|None}.
    Si se pasa `meta`, se llena con:
        meta["modelo"]   -> modelo que respondió (o "" si ninguno)
        meta["fallos"]   -> ["gemini-x (cuota agotada)", ...] modelos que fallaron antes
        meta["detalle"]  -> texto explicativo si no hubo respuesta
    """
    if meta is None:
        meta = {}
    meta.update({"modelo": "", "fallos": [], "detalle": ""})
    marks = {"op": None, "ed": None}

    # Reorganizamos la lista para intentar primero con el modelo que pasas por argumento,
    # y si falla por cuota, usamos los demás de respaldo (o usamos la lista restringida).
    modelos_a_probar = (
        list(modelos_permitidos)
        if modelos_permitidos is not None
        else [model] + [m for m in MODELOS_FALLBACK if m != model]
    )
    if not modelos_a_probar:
        meta["detalle"] = "no hay modelos superiores disponibles"
        log.warning("No hay modelos de Gemini disponibles para probar.")
        return marks

    api_key = load_gemini_key()
    if not api_key:
        meta["detalle"] = "falta la clave de Gemini"
        log.warning("Plan B no disponible: falta la clave (GEMINI_API_KEY o %s).",
                    SCRIPT_DIR / "gemini_key.txt")
        return marks

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log.error("Falta la librería de Gemini. Ejecuta: pip install google-genai")
        meta["detalle"] = "falta la librería google-genai"
        return marks

    # Con límite de espera: sin esto, una petición lenta parece "colgada"
    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))

    with tempfile.TemporaryDirectory() as tmp:
        proxy = Path(tmp) / "proxy.mp4"
        make_proxy(src, proxy, threads)

        uploaded = client.files.upload(file=str(proxy))
        try:
            while uploaded.state.name == "PROCESSING":
                time.sleep(2)
                uploaded = client.files.get(name=uploaded.name)
            if uploaded.state.name != "ACTIVE":
                raise RuntimeError(
                    f"Archivo en Gemini en estado {uploaded.state.name}")

            data = None
            ultimo_motivo = "sin respuesta"
            # Iteramos sobre los modelos disponibles para el fallback
            for modelo_actual in modelos_a_probar:
                log.info("🤖 Intentando análisis con el modelo: %s", modelo_actual)

                for attempt in range(1, 4):
                    try:
                        resp = client.models.generate_content(
                            model=modelo_actual,
                            contents=[
                                uploaded, GEMINI_PROMPT.format(dur=duration)],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"),
                        )
                        data = json.loads(resp.text)
                        meta["modelo"] = modelo_actual
                        break  # Éxito, salimos del bucle de reintentos
                    except Exception as e:
                        error_str = str(e)
                        ultimo_motivo = _motivo_corto(e)
                        log.warning("⚠️ %s - Intento %d/3 falló: %s",
                                    modelo_actual, attempt, e)

                        # Si es error de cuota (429 / ResourceExhausted), rompemos para cambiar de modelo inmediatamente
                        if "429" in error_str or "ResourceExhausted" in error_str or "quota" in error_str.lower():
                            log.warning(
                                "🔄 Cuota agotada detectada en %s. Cambiando de modelo...", modelo_actual)
                            break

                        time.sleep(5 * attempt)

                if data:
                    break  # Si obtuvimos datos con éxito, no probamos más modelos
                meta["fallos"].append(f"{modelo_actual} ({ultimo_motivo})")

            if not data:
                log.error(
                    "❌ Todos los modelos de Gemini fallaron o agotaron su cuota.")
                meta["detalle"] = "todos los modelos fallaron: " + \
                    "; ".join(meta["fallos"])
                return marks

        finally:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass

    if isinstance(data, list) and data:
        data = data[0]
    if data.get("op_start") is not None and data.get("op_end") is not None:
        marks["op"] = [float(data["op_start"]), float(data["op_end"])]
    if data.get("ed_start") is not None and data.get("ed_end") is not None:
        marks["ed"] = [float(data["ed_start"]), float(data["ed_end"])]
    return marks


# --------------------------------------------------------------------------- #
# Registro de Gemini en Google Sheets (columnas J:L de la hoja "Animes")
# --------------------------------------------------------------------------- #
INDICE_DESCARGAS = "descargas_index.json"   # lo escribe descargar.py en la carpeta de entrada
_sheets_estado = {"service": None, "intentado": False, "filas": None}


def _importar_base_excel():
    """
    Importa base_excel sin romper el logging: ese módulo reconfigura el logger
    raíz al importarse y descartaría el archivo anime_x3.log.
    """
    if "base_excel" in sys.modules:
        return sys.modules["base_excel"]
    raiz = logging.getLogger()
    handlers, nivel = list(raiz.handlers), raiz.level
    try:
        import base_excel
    finally:
        extra = [h for h in raiz.handlers if h not in handlers]
        raiz.handlers = handlers + extra
        raiz.setLevel(nivel)
    return base_excel


def _servicio_sheets():
    """Conexión a Sheets, creada una sola vez. None si no está disponible."""
    if not _sheets_estado["intentado"]:
        _sheets_estado["intentado"] = True
        try:
            _sheets_estado["service"] = _importar_base_excel().obtener_conexion_google_sheets()
        except Exception as e:
            log.warning("  Sheets no disponible, no se guardará lo de Gemini: %s", e)
    return _sheets_estado["service"]


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _ubicar_episodio(src: Path, in_dir: Path) -> tuple[str, str] | None:
    """
    Devuelve (nombre_anime, episodio) del archivo.
    1) Índice que escribe descargar.py al terminar cada descarga (exacto).
    2) Si no está, se compara el nombre del archivo con las filas de la hoja.
    """
    indice = in_dir / INDICE_DESCARGAS
    if indice.exists():
        try:
            datos = json.loads(indice.read_text(encoding="utf-8"))
            item = datos.get(str(src.resolve()).lower())
            if item:
                return str(item["nombre"]), str(item["episodio"])
        except Exception as e:
            log.warning("  No se pudo leer %s: %s", INDICE_DESCARGAS, e)

    service = _servicio_sheets()
    if not service:
        return None
    try:
        filas = _importar_base_excel().leer_animes_pendientes(service)
    except Exception:
        return None

    try:
        rel_src = src.resolve().relative_to(in_dir.resolve()).as_posix().lower()
    except ValueError:
        rel_src = src.name.lower()
    nombre_src = src.name.lower()

    for f in filas:
        archivo_sheet = str(f.get("archivo", "")).strip().replace("\\", "/").lower()
        if archivo_sheet and not archivo_sheet.startswith("[eliminado]"):
            if archivo_sheet == rel_src or Path(archivo_sheet).name == nombre_src:
                return str(f["nombre"]), str(f["episodio"])

    archivo = _norm(src.stem)
    numeros = {int(n) for n in re.findall(r"\d+", archivo)}
    mejor, largo = None, 0
    for f in filas:
        nombre = _norm(f.get("nombre", ""))
        ep = str(f.get("episodio", "")).strip()
        if nombre and nombre in archivo and ep.isdigit() and int(ep) in numeros:
            if len(nombre) > largo:       # "X II" gana a "X" si el archivo dice "X II"
                mejor, largo = (f["nombre"], ep), len(nombre)
    return mejor


def registrar_gemini(
    src: Path,
    in_dir: Path,
    modelo: str,
    detalle: str,
    ubicacion: tuple[str, str] | None = None,
) -> None:
    """Guarda modelo, detalle y fecha de procesamiento de Gemini en la hoja."""
    try:
        if ubicacion is None:
            ubicacion = _ubicar_episodio(src, in_dir)
        if not ubicacion:
            log.warning("  Sheets: no pude saber a qué anime/episodio corresponde '%s'; "
                        "no se guardó lo de Gemini.", src.name)
            return
        service = _servicio_sheets()
        if not service:
            return
        _importar_base_excel().registrar_gemini_en_sheets(
            service, ubicacion[0], ubicacion[1], modelo, detalle,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        log.warning("  No se pudo registrar Gemini en Sheets: %s", e)


# --------------------------------------------------------------------------- #
# Validación y construcción de tramos
# --------------------------------------------------------------------------- #
def validate_range(r, duration: float, name: str | None = None, reasons: list | None = None):
    """Devuelve (inicio, fin) o None. Con `name` informa por qué se descarta
    (en el log y, si se pasa `reasons`, también en esa lista)."""
    def say(level, msg, *a):
        if name:
            log.log(level, msg, *a)
            if reasons is not None:
                reasons.append((msg % a).strip().rstrip(".").replace("Gemini: ", ""))

    if not r or r[0] is None or r[1] is None:
        say(logging.INFO, "  Gemini: sin %s.", name)
        return None
    s, e = float(r[0]), float(r[1])
    if s >= duration:
        say(logging.WARNING, "  %s descartado: empieza en %.0f s pero el video dura %.0f s.",
            name, s, duration)
        return None
    s, e = max(0.0, s), min(duration, e)
    length = e - s
    if length <= 0:                       # [0, 0] = "no existe"
        say(logging.INFO, "  Gemini: sin %s.", name)
        return None
    if not (MIN_OPED <= length <= MAX_OPED):
        say(logging.WARNING, "  %s descartado: dura %.0f s (válido: %d-%d s).",
            name, length, MIN_OPED, MAX_OPED)
        return None
    return (s, e)


def validate_marks(raw: dict, duration: float, verbose: bool = True,
                   reasons: list | None = None) -> dict:
    return {k: validate_range(raw.get(k), duration, k.upper() if verbose else None, reasons)
            for k in ("op", "ed")}


def build_segments(duration: float, op, ed) -> list[tuple[float, float, bool]]:
    """Devuelve [(inicio, fin, acelerar?)]. Hasta 5 tramos."""
    normals = sorted(r for r in (op, ed) if r)
    if len(normals) == 2 and normals[0][1] > normals[1][0]:
        log.warning("OP y ED se solapan; se ignora el ED.")
        normals = [normals[0]]

    segs, cur = [], 0.0
    for s, e in normals:
        segs.append((cur, s, True))
        segs.append((s, e, False))
        cur = e
    segs.append((cur, duration, True))
    return [(s, e, f) for s, e, f in segs if e - s >= MIN_SEGMENT]


# --------------------------------------------------------------------------- #
# FFmpeg
# --------------------------------------------------------------------------- #
def probe(path: Path) -> dict:
    return probe_ffprobe(path) if FFPROBE else probe_ffmpeg(path)


def probe_ffmpeg(path: Path) -> dict:
    """Plan sin ffprobe: lee duración, fps y audio desde la salida de 'ffmpeg -i'."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", str(path)],
                       capture_output=True, text=True, errors="replace")
    text = r.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        raise RuntimeError(
            "No pude leer la duración con ffmpeg: " + text[-300:])
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    fps_m = re.search(r"Video:.*?,\s*(\d+(?:\.\d+)?)\s*fps", text)
    return {
        "duration": duration,
        "fps": fps_m[1] if fps_m else "24",
        "has_audio": bool(re.search(r"Stream #0:\d+.*?: Audio:", text)),
    }


def probe_ffprobe(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    streams = data["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    fps = "24"
    for key in ("avg_frame_rate", "r_frame_rate"):
        val = v.get(key, "0/0")
        num, _, den = val.partition("/")
        if float(num or 0) > 0 and float(den or 1) > 0:
            fps = val
            break
    return {
        "duration": float(data["format"]["duration"]),
        "fps": fps,
        "has_audio": any(s["codec_type"] == "audio" for s in streams),
    }


def atempo_chain(speed: float) -> str:
    """atempo clásico acepta 0.5-2.0 por filtro; se encadena para valores mayores."""
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)


def render(src: Path, tmp_dst: Path, segs, speed: float, info: dict, threads: int, preset: str, crf: int) -> None:
    """Genera el video acelerado en tmp_dst (archivo temporal .part.mp4)."""
    fps, has_audio = info["fps"], info["has_audio"]
    parts, labels = [], []
    for i, (s, e, fast) in enumerate(segs):
        sp = speed if fast else 1.0
        parts.append(
            f"[0:v:0]trim=start={s:.3f}:end={e:.3f},setpts=(PTS-STARTPTS)/{sp},fps={fps}[v{i}]"
        )
        labels.append(f"[v{i}]")
        if has_audio:
            achain = f"[0:a:0]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS"
            if fast:
                achain += "," + atempo_chain(sp)
            parts.append(achain + f"[a{i}]")
            labels.append(f"[a{i}]")

    a_flag = 1 if has_audio else 0
    out_labels = "[outv][outa]" if has_audio else "[outv]"
    parts.append(
        f"{''.join(labels)}concat=n={len(segs)}:v=1:a={a_flag}{out_labels}")

    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-threads", str(threads), "-filter_complex_threads", "1",
        "-i", str(src),
        "-filter_complex", ";".join(parts),
        "-map", "[outv]",
    ]
    if has_audio:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "128k"]
    cmd += [
        "-c:v", "libx264", "-preset", preset, "-crf", str(
            crf), "-pix_fmt", "yuv420p",
        "-threads", str(threads), "-movflags", "+faststart", "-f", "mp4", str(tmp_dst),
    ]
    r = run_low_priority(cmd)
    if r.returncode != 0:
        tmp_dst.unlink(missing_ok=True)
        raise RuntimeError(r.stderr[-800:])


# --------------------------------------------------------------------------- #
# Orquestación por archivo
# --------------------------------------------------------------------------- #
def get_marks(
    src: Path,
    info: dict,
    args,
    cache: dict,
    cache_path: Path,
    forzar_gemini: bool = False,
    modelos_permitidos: list[str] | None = None,
    registrar_fallo_sheets: bool = True,
    registrar_resultado_sheets: bool = True,
    ubicacion_sheets: tuple[str, str] | None = None,
) -> tuple[dict, str, dict]:
    """Devuelve (marcas, fuente, detalle). detalle = {"model", "reason", "intentos"}."""
    duration = info["duration"]
    gkey = f"gemini:{src.name}:{src.stat().st_size}"
    marks = {"op": None, "ed": None}
    detail = {"model": None, "reason": None, "intentos": []}

    if not forzar_gemini and gkey in cache["marks"]:
        entry = cache["marks"][gkey]
        marks = validate_marks(entry, duration, verbose=False)
        if marks["op"] or marks["ed"]:
            log.info("  Marcas de Gemini tomadas de la caché.")
            detail["model"] = f"{entry.get('model') or 'modelo desconocido'} (marcas guardadas en caché)"
        else:
            log.info(
                "  La caché de este episodio no tiene marcas válidas; se consulta de nuevo.")

    if not (marks["op"] or marks["ed"]):
        log.info("  Consultando Gemini para detectar OP/ED...")
        meta: dict = {}
        try:
            raw = gemini_marks(
                src, duration, args.threads, args.gemini_model, meta,
                modelos_permitidos=modelos_permitidos,
            )
        except Exception as e:
            log.error("  Gemini falló: %s", e)
            raw = {"op": None, "ed": None}
            meta.setdefault("modelo", "")
            meta.setdefault("fallos", [])
            meta["detalle"] = f"error al preparar o subir el video a Gemini: {str(e)[-250:]}"
        reasons: list[str] = []
        marks = validate_marks(raw, duration, reasons=reasons)
        detail["intentos"] = meta.get("fallos", [])

        # ---- Resultado para la hoja ----
        def _fmt(r):
            return f"{r[0]:.0f}-{r[1]:.0f}s" if r else "no tiene"
        modelo_ok = meta.get("modelo", "")
        if marks["op"] or marks["ed"]:
            detalle = f"✅ Funcionó | OP: {_fmt(marks['op'])} | ED: {_fmt(marks['ed'])}"
            if meta.get("fallos"):
                detalle += " | antes falló: " + "; ".join(meta["fallos"])
        elif modelo_ok:
            detalle = "❌ No funcionó: Gemini respondió pero sin marcas válidas de OP/ED"
        else:
            detalle = "❌ No funcionó: " + (meta.get("detalle") or "sin respuesta")
        # Si ningún modelo respondió, se deja constancia del primero que se intentó
        modelo_hoja = modelo_ok or f"{args.gemini_model} (sin respuesta)"
        if registrar_resultado_sheets and (
                (marks["op"] or marks["ed"]) or registrar_fallo_sheets):
            registrar_gemini(
                src, cache_path.parent, modelo_hoja, detalle,
                ubicacion=ubicacion_sheets,
            )

        if marks["op"] or marks["ed"]:
            detail["model"] = modelo_ok or "modelo desconocido"
            # Solo se guarda lo válido: así nunca se reutiliza una respuesta mala
            cache["marks"][gkey] = {
                **{k: list(v) if v else None for k, v in marks.items()},
                "model": modelo_ok}
            save_cache(cache_path, cache)
        elif modelo_ok:
            detail["reason"] = (f"Gemini ({modelo_ok}) respondió, pero sin marcas utilizables"
                                + (": " + "; ".join(reasons) if reasons else ""))
        else:
            detail["reason"] = meta.get("detalle") or "sin respuesta"

    if marks["op"] or marks["ed"]:
        return marks, "Gemini", detail
    return marks, "none", detail


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 1
    while True:
        cand = p.with_name(f"{p.stem}_{i}{p.suffix}")
        if not cand.exists():
            return cand
        i += 1


def process_file(src: Path, args, in_dir: Path, cache, cache_path) -> bool:
    rel = src.relative_to(in_dir)
    # Junto al episodio (p. ej. dentro de la carpeta de la fecha) van las dos subcarpetas
    processed_dir = src.parent / PROCESSED_DIRNAME
    originals_dir = src.parent / ORIGINALS_DIRNAME
    dst = processed_dir / f"{src.stem}.mp4"
    if dst.exists():
        log.warning("Ya existe '%s'; se omite y el original no se toca.", dst)
        return True

    t0 = time.time()
    log.info("Procesando: %s", rel)
    try:
        info = probe(src)
    except Exception as e:
        causa = (f"ffprobe terminó con error {e.returncode}"
                 if isinstance(e, subprocess.CalledProcessError) else str(e)[-300:])
        raise RuntimeError(
            f"no pude leer el video (¿archivo dañado o incompleto?): {causa}") from e

    marks, source, detail = get_marks(src, info, args, cache, cache_path)
    if source == "none":
        log.error(
            "  Sin marcas de tiempo para %s. Se deja el archivo sin tocar.", rel)
        intentos = ""
        if detail["intentos"] and "todos los modelos" not in (detail["reason"] or ""):
            intentos = "\n⚠️ Modelos que fallaron: " + " | ".join(detail["intentos"])
        notificar(f"❌ No se pudo procesar el episodio (x{args.speed:g})\n"
                  f"📁 {rel}\n"
                  f"❗ Motivo: {detail['reason'] or 'Gemini no devolvió marcas de OP/ED'}"
                  f"{intentos}\n"
                  f"↩️ El original quedó sin tocar.")
        return False

    segs = build_segments(info["duration"], marks["op"], marks["ed"])

    def fmt(r):
        return f"{r[0]:.0f}-{r[1]:.0f} s" if r else "no tiene"
    log.info("  Marcas vía %s | OP: %s | ED: %s | %d tramos",
             source, fmt(marks["op"]), fmt(marks["ed"]), len(segs))

    processed_dir.mkdir(exist_ok=True)
    tmp_dst = dst.with_name(dst.stem + ".part.mp4")
    try:
        render(src, tmp_dst, segs, args.speed, info,
               args.threads, args.preset, args.crf)
    except Exception as e:
        raise RuntimeError("falló FFmpeg al acelerar el video (el original no se tocó): "
                           f"{str(e)[-400:]}") from e

    # 1) el original se mueve a "originales" (mismo nombre)
    # 2) el acelerado queda en "procesados"
    originals_dir.mkdir(exist_ok=True)
    original = unique_path(originals_dir / src.name)
    shutil.move(str(src), str(original))
    try:
        tmp_dst.replace(dst)
    except Exception:
        shutil.move(str(original), str(src))     # deshacer si algo falla
        tmp_dst.unlink(missing_ok=True)
        raise

    log.info("  OK -> %s", dst.relative_to(in_dir))
    log.info("  Original -> %s", original.relative_to(in_dir))

    # ---- Aviso por Telegram ----
    nueva = sum((e - s) / (args.speed if fast else 1.0) for s, e, fast in segs)
    previos = ""
    if detail["intentos"]:
        previos = "\n⚠️ Antes fallaron: " + " | ".join(detail["intentos"])
    notificar(f"✅ Episodio procesado (x{args.speed:g})\n"
              f"📁 {rel}\n"
              f"🤖 Modelo de Gemini: {detail['model'] or 'desconocido'}"
              f"{previos}\n"
              f"🎬 OP: {fmt(marks['op'])} | ED: {fmt(marks['ed'])}\n"
              f"⏱ Duración: {fmt_dur(info['duration'])} → {fmt_dur(nueva)}\n"
              f"🕒 Tiempo de proceso: {fmt_dur(time.time() - t0)}")
    return True


def _es_subruta(base_dir: Path, p: Path) -> bool:
    try:
        p.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _buscar_archivos_reproceso(in_dir: Path, item: dict, hoy: str) -> tuple[Path | None, Path | None]:
    """
    Localiza (archivo_original, archivo_procesado_anterior) para una fila de Sheets.
    """
    nombre = str(item.get("nombre", "")).strip()
    episodio = str(item.get("episodio", "")).strip()
    archivo_rel = str(item.get("archivo", "")).strip().replace("\\", "/")

    posibles_pares: list[tuple[Path, Path]] = []
    if archivo_rel and not archivo_rel.lower().startswith("[eliminado]"):
        rel = Path(archivo_rel.lstrip("/"))
        if not rel.is_absolute() and ".." not in rel.parts:
            posibles_pares.append((
                in_dir / rel.parent / ORIGINALS_DIRNAME / rel.name,
                in_dir / rel.parent / PROCESSED_DIRNAME / f"{rel.stem}.mp4",
            ))
            if rel.parent != Path("."):
                posibles_pares.append((
                    in_dir / ORIGINALS_DIRNAME / rel.name,
                    in_dir / PROCESSED_DIRNAME / f"{rel.stem}.mp4",
                ))

    # Respaldo 1: descargas_index.json
    indice_path = in_dir / INDICE_DESCARGAS
    if indice_path.is_file():
        try:
            datos = json.loads(indice_path.read_text(encoding="utf-8"))
            for ruta_abs, info in datos.items():
                if not isinstance(info, dict):
                    continue
                if (
                    str(info.get("nombre", "")).strip().lower() == nombre.lower()
                    and str(info.get("episodio", "")).strip() == episodio
                ):
                    p = Path(ruta_abs)
                    posibles_pares.append((
                        p.parent / ORIGINALS_DIRNAME / p.name,
                        p.parent / PROCESSED_DIRNAME / f"{p.stem}.mp4",
                    ))
        except Exception:
            pass

    for orig, proc in posibles_pares:
        if orig.is_file() and _es_subruta(in_dir, orig):
            proc_existente = proc if (proc.is_file() and _es_subruta(in_dir, proc)) else None
            return orig, proc_existente

    # Respaldo 2: escanear carpeta del día (<in_dir>/<hoy>/originales)
    orig_dir_hoy = in_dir / hoy / ORIGINALS_DIRNAME
    if orig_dir_hoy.is_dir():
        for cand in sorted(orig_dir_hoy.iterdir()):
            if not cand.is_file() or cand.suffix.lower() not in VIDEO_EXTS:
                continue
            ubic = _ubicar_episodio(cand, in_dir)
            if ubic and ubic[0].strip().lower() == nombre.lower() and str(ubic[1]).strip() == episodio:
                proc = in_dir / hoy / PROCESSED_DIRNAME / f"{cand.stem}.mp4"
                return cand, proc if proc.is_file() else None

    return None, None


def _reprocesar_episodio_superior(
    item: dict,
    original: Path,
    procesado_anterior: Path | None,
    args,
    in_dir: Path,
    cache: dict,
    cache_path: Path,
) -> str:
    """
    Reprocesa `original` exigiendo un modelo estrictamente superior al previo.
    Solo elimina `procesado_anterior` si el nuevo render termina con éxito.
    Devuelve 'ok', 'sin_mejora' o 'error'.
    """
    nombre = str(item.get("nombre", "")).strip()
    episodio = str(item.get("episodio", "")).strip()
    modelo_anterior = str(item.get("modelo_gemini", "")).strip()
    v_anterior = _version_modelo(modelo_anterior)
    if v_anterior is None:
        return "sin_mejora"

    candidatos_modelos = _modelos_superiores(args.gemini_model, v_anterior)
    if not candidatos_modelos:
        log.warning("  No hay modelos superiores a '%s' configurados para %s Ep. %s.",
                    modelo_anterior, nombre, episodio)
        return "sin_mejora"

    t0 = time.time()
    rel = original.relative_to(in_dir)
    log.info("♻️ Reprocesando (%s < 3.6): %s | modelos permitidos: %s",
             modelo_anterior, rel, ", ".join(candidatos_modelos))

    try:
        info = probe(original)
    except Exception as e:
        log.error("  No pude leer el original %s: %s", original.name, e)
        return "error"

    marks, source, detail = get_marks(
        original, info, args, cache, cache_path,
        forzar_gemini=True,
        modelos_permitidos=candidatos_modelos,
        registrar_fallo_sheets=False,
        registrar_resultado_sheets=False,
        ubicacion_sheets=(nombre, episodio),
    )

    modelo_nuevo = detail.get("model") or ""
    v_nuevo = _version_modelo(modelo_nuevo)
    if source == "none" or v_nuevo is None or v_nuevo <= v_anterior:
        log.warning(
            "  No se obtuvo un modelo superior a '%s' para %s Ep. %s (%s). "
            "Se conserva el procesado anterior.",
            modelo_anterior, nombre, episodio,
            detail.get("reason") or "sin respuesta",
        )
        return "sin_mejora"

    segs = build_segments(info["duration"], marks["op"], marks["ed"])

    def fmt(r):
        return f"{r[0]:.0f}-{r[1]:.0f} s" if r else "no tiene"

    log.info("  Mejora confirmada (%s -> %s) | OP: %s | ED: %s | %d tramos",
             modelo_anterior, modelo_nuevo, fmt(marks["op"]), fmt(marks["ed"]), len(segs))

    processed_dir = original.parent.parent / PROCESSED_DIRNAME
    processed_dir.mkdir(exist_ok=True)
    dst = procesado_anterior if procesado_anterior else (processed_dir / f"{original.stem}.mp4")
    tmp_dst = dst.with_name(dst.stem + ".reproceso.part.mp4")

    try:
        render(original, tmp_dst, segs, args.speed, info,
               args.threads, args.preset, args.crf)
    except Exception as e:
        log.error("  Falló FFmpeg al reprocesar %s (se conserva el procesado anterior): %s",
                  original.name, str(e)[-400:])
        return "error"

    try:
        tmp_dst.replace(dst)
    except Exception as e:
        tmp_dst.unlink(missing_ok=True)
        log.error("  ❌ No se pudo guardar el nuevo procesado %s: %s", dst.name, e)
        return "error"

    if procesado_anterior:
        log.info("  🗑️ Procesado anterior reemplazado: %s",
                 procesado_anterior.relative_to(in_dir))

    def _fmt(r):
        return f"{r[0]:.0f}-{r[1]:.0f}s" if r else "no tiene"

    detalle = f"✅ Funcionó | OP: {_fmt(marks['op'])} | ED: {_fmt(marks['ed'])}"
    if detail["intentos"]:
        detalle += " | antes falló: " + "; ".join(detail["intentos"])
    registrar_gemini(
        original, in_dir, modelo_nuevo, detalle,
        ubicacion=(nombre, episodio),
    )

    log.info("  OK (reprocesado) -> %s", dst.relative_to(in_dir))

    nueva = sum((e - s) / (args.speed if fast else 1.0) for s, e, fast in segs)
    previos = ""
    if detail["intentos"]:
        previos = "\n⚠️ Antes fallaron: " + " | ".join(detail["intentos"])
    notificar(f"♻️ Episodio reprocesado con modelo superior (x{args.speed:g})\n"
              f"📁 {dst.relative_to(in_dir)}\n"
              f"🤖 Modelo: {modelo_anterior} → {modelo_nuevo}"
              f"{previos}\n"
              f"🎬 OP: {fmt(marks['op'])} | ED: {fmt(marks['ed'])}\n"
              f"⏱ Duración: {fmt_dur(info['duration'])} → {fmt_dur(nueva)}\n"
              f"🕒 Tiempo de proceso: {fmt_dur(time.time() - t0)}")
    return "ok"


def reprocesar_inferiores_del_dia(args, in_dir: Path, cache: dict, cache_path: Path) -> None:
    """
    Revisa Google Sheets para el día actual: los episodios procesados con un
    modelo Gemini inferior a 3.6 se reprocesan desde 'originales/' exigiendo
    un modelo estrictamente superior y eliminando el procesado anterior.
    """
    service = _servicio_sheets()
    if not service:
        log.warning("⚠️ Sheets no disponible: se omite la revisión de modelos < 3.6.")
        return

    try:
        filas = _importar_base_excel().leer_animes_pendientes(service)
    except Exception as e:
        log.warning("⚠️ No se pudo leer Google Sheets para revisar modelos < 3.6: %s", e)
        return

    hoy = datetime.now().strftime("%Y-%m-%d")
    candidatos = []
    vistos = set()

    for item in filas:
        archivo = str(item.get("archivo", "")).strip().lower()
        if archivo.startswith("[eliminado]"):
            continue

        fecha_g = str(item.get("fecha_gemini", "")).strip()
        fecha_d = str(item.get("fecha_descarga", "")).strip()
        es_hoy = fecha_g.startswith(hoy) if fecha_g else fecha_d.startswith(hoy)
        if not es_hoy:
            continue

        modelo = str(item.get("modelo_gemini", "")).strip()
        if not modelo or "sin respuesta" in modelo.lower():
            continue

        ver = _version_modelo(modelo)
        if ver is None or ver >= VERSION_MODELO_MINIMA:
            continue

        clave = (str(item.get("nombre", "")).strip().lower(), str(item.get("episodio", "")).strip())
        if clave in vistos:
            continue
        vistos.add(clave)
        candidatos.append(item)

    if not candidatos:
        log.info("✨ Revisión de las 19:00: no hay episodios de hoy (%s) con modelo < 3.6.", hoy)
        return

    log.info("🔍 Revisión de las 19:00: %d episodio(s) de hoy (%s) con modelo < 3.6.",
             len(candidatos), hoy)

    ok = sin_mejora = err = 0
    for item in candidatos:
        original, proc_anterior = _buscar_archivos_reproceso(in_dir, item, hoy)
        if not original:
            log.warning("  ⚠️ No se encontró archivo original en '%s' para %s Ep. %s (%s).",
                        ORIGINALS_DIRNAME, item.get("nombre"), item.get("episodio"),
                        item.get("modelo_gemini"))
            err += 1
            continue

        res = _reprocesar_episodio_superior(
            item, original, proc_anterior, args, in_dir, cache, cache_path
        )
        if res == "ok":
            ok += 1
        elif res == "sin_mejora":
            sin_mejora += 1
        else:
            err += 1

    log.info("♻️ Reproceso 19:00 terminado. Mejorados: %d | Sin mejora: %d | Errores: %d",
             ok, sin_mejora, err)


def ejecucion_recortador() -> int:
    ap = argparse.ArgumentParser(
        description="Anime xN con OP/ED a velocidad normal.")
    ap.add_argument("input", type=Path, nargs="?", default=Path(DEFAULT_INPUT),
                    help="Carpeta de origen (se recorre recursivamente)")
    ap.add_argument("output", type=Path, nargs="?", default=None,
                    help="(ignorado) los procesados van a <carpeta del episodio>/procesados")
    ap.add_argument("--speed", type=float, default=3.0,
                    help="Factor de aceleración (def: 3)")
    ap.add_argument("--threads", type=int, default=2,
                    help="Hilos de FFmpeg (def: 2)")
    ap.add_argument("--preset", default="veryfast",
                    help="Preset x264 (def: veryfast)")
    ap.add_argument("--crf", type=int, default=23,
                    help="Calidad x264 (def: 23)")
    ap.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    ap.add_argument("--forzar", action="store_true",
                    help="Ejecuta aunque esté fuera de horario (15:00 / 19:00)")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    in_dir = args.input.resolve()
    if not in_dir.is_dir():
        print(f"La carpeta de entrada no existe: {in_dir}")
        notificar("❌ El procesador x3 no pudo iniciar\n"
                  f"❗ Motivo: la carpeta de entrada no existe: {in_dir}")
        return 1

    # Log y caché quedan en la carpeta de entrada (se conserva la caché existente)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(in_dir / "anime_x3.log", encoding="utf-8")],
    )
    if args.output:
        log.warning("El segundo argumento (%s) se ignora: los procesados van a "
                    "<carpeta del episodio>/%s.", args.output, PROCESSED_DIRNAME)

    ahora = datetime.now()
    hora = ahora.hour
    hoy = ahora.strftime("%Y-%m-%d")
    cache_path = in_dir / "anime_x3_cache.json"
    cache = load_cache(cache_path)

    if not args.forzar:
        if hora not in HORAS_EJECUCION:
            log.info("⏰ Fuera de horario de recorte (solo 15:00 y 19:00). Hora actual: %02d:%02d.",
                     hora, ahora.minute)
            return 0
        runs = cache.setdefault("runs", {})
        if hora in runs.get(hoy, []):
            log.info("⏭️ El recorte de las %02d:00 ya se ejecutó hoy (%s); se omite.", hora, hoy)
            return 0

    if not FFMPEG:
        log.error(
            "No encuentro ffmpeg. Pon ffmpeg.exe en %s o agrégalo al PATH.", SCRIPT_DIR)
        notificar("❌ El procesador x3 no pudo iniciar\n"
                  f"❗ Motivo: no encuentro ffmpeg (debe estar en {SCRIPT_DIR} o en el PATH)")
        return 1
    log.info("ffmpeg: %s", FFMPEG)
    if FFPROBE:
        log.info("ffprobe: %s", FFPROBE)
    else:
        log.info(
            "ffprobe no encontrado: se analizarán los videos con ffmpeg (funciona igual).")

    if not load_gemini_key():
        log.error("Falta la clave de Gemini (GEMINI_API_KEY en .env/entorno o %s).",
                  SCRIPT_DIR / "gemini_key.txt")
        notificar("❌ El procesador x3 no pudo iniciar\n"
                  "❗ Motivo: falta la clave de Gemini (GEMINI_API_KEY)")
        return 1

    if not args.forzar:
        fecha_limite = (ahora - timedelta(days=7)).strftime("%Y-%m-%d")
        runs = {k: v for k, v in cache.get("runs", {}).items() if k >= fecha_limite}
        runs.setdefault(hoy, []).append(hora)
        cache["runs"] = runs
        save_cache(cache_path, cache)

    skip_dirs = {PROCESSED_DIRNAME.lower(), ORIGINALS_DIRNAME.lower()}

    def in_output_folder(p: Path) -> bool:
        """True si el archivo ya está dentro de una carpeta 'procesados' u 'originales'."""
        return any(part.lower() in skip_dirs for part in p.relative_to(in_dir).parts[:-1])

    all_videos = [p for p in in_dir.rglob("*")
                  if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not in_output_folder(p)]
    # Protección para archivos de versiones anteriores (renombrados a "Original_..."):
    # el "Original_X" y el "X" procesado que quedó a su lado no se vuelven a acelerar.
    has_legacy_original = {(p.parent, p.stem.lower()[len(LEGACY_PREFIX):])
                           for p in all_videos if p.stem.lower().startswith(LEGACY_PREFIX)}

    def is_candidate(p: Path) -> bool:
        stem = p.stem.lower()
        if stem.startswith(LEGACY_PREFIX) or (p.parent, stem) in has_legacy_original:
            return False
        if stem.endswith(".part"):                  # temporal de una corrida interrumpida
            return False
        # "[x3].mp4" de versiones anteriores
        if OUTPUT_NAME_RE.search(p.stem):
            return False
        if cache.get("done", {}).get(str(p.resolve()).lower()) == p.stat().st_size:
            return False                            # registrado como procesado antes
        return True

    files = sorted(p for p in all_videos if is_candidate(p))
    log.info("Encontrados %d episodios en %s", len(files), in_dir)

    ok = fail = 0
    interrumpido = False
    try:
        for n, src in enumerate(files, 1):
            log.info("[%d/%d]", n, len(files))
            try:
                if process_file(src, args, in_dir, cache, cache_path):
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                fail += 1
                log.error("  Error en %s: %s", src.name, e)
                notificar(f"❌ Error al procesar el episodio (x{args.speed:g})\n"
                          f"📁 {src.relative_to(in_dir)}\n"
                          f"❗ Motivo: {str(e)[-500:]}")
    except KeyboardInterrupt:
        interrumpido = True
        log.warning("Interrumpido por el usuario.")
        if not args.forzar and hoy in cache.get("runs", {}) and hora in cache["runs"][hoy]:
            cache["runs"][hoy].remove(hora)
            save_cache(cache_path, cache)

    log.info("Terminado. OK: %d | Fallidos/sin marcas: %d", ok, fail)

    if not interrumpido and hora == HORA_REPROCESO_MODELO:
        reprocesar_inferiores_del_dia(args, in_dir, cache, cache_path)

    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(ejecucion_recortador())
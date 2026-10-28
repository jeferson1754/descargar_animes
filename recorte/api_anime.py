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
    El episodio original NO se borra ni se mueve: se renombra a "Original_<nombre>"
    en su misma carpeta, y el episodio procesado queda con el nombre original (.mp4).

Requisitos:
    pip install google-genai python-dotenv
    ffmpeg.exe junto al script (o ffmpeg en el PATH); ffprobe es opcional
    Clave de Gemini: variable GEMINI_API_KEY o archivo gemini_key.txt junto al script

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
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()
# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v"}

# --- Rutas por defecto: se usan si ejecutas sin argumentos (botón "Run" de VS Code) ---
DEFAULT_INPUT = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"
# <carpeta del episodio>/procesados  (acelerados)
PROCESSED_DIRNAME = "procesados"
# <carpeta del episodio>/originales  (originales)
ORIGINALS_DIRNAME = "originales"
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

MODELOS_FALLBACK = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite"
]

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


def gemini_marks(src: Path, duration: float, threads: int, model: str) -> dict:
    marks = {"op": None, "ed": None}
    api_key = load_gemini_key()
    if not api_key:
        log.warning("Plan B no disponible: falta la clave (GEMINI_API_KEY o %s).",
                    SCRIPT_DIR / "gemini_key.txt")
        return marks

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log.error("Falta la librería de Gemini. Ejecuta: pip install google-genai")
        return marks

    # Con límite de espera: sin esto, una petición lenta parece "colgada"
    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))

    # Reorganizamos la lista para intentar primero con el modelo que pasas por argumento,
    # y si falla por cuota, usamos los demás de respaldo.
    modelos_a_probar = [model] + [m for m in MODELOS_FALLBACK if m != model]

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
                        break  # Éxito, salimos del bucle de reintentos
                    except Exception as e:
                        error_str = str(e)
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

            if not data:
                log.error(
                    "❌ Todos los modelos de Gemini fallaron o agotaron su cuota.")
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
# Validación y construcción de tramos
# --------------------------------------------------------------------------- #
def validate_range(r, duration: float, name: str | None = None):
    """Devuelve (inicio, fin) o None. Con `name` informa por qué se descarta."""
    def say(level, msg, *a):
        if name:
            log.log(level, msg, *a)

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


def validate_marks(raw: dict, duration: float, verbose: bool = True) -> dict:
    return {k: validate_range(raw.get(k), duration, k.upper() if verbose else None)
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
def get_marks(src: Path, info: dict, args, cache: dict, cache_path: Path) -> tuple[dict, str]:
    duration = info["duration"]
    gkey = f"gemini:{src.name}:{src.stat().st_size}"
    marks = {"op": None, "ed": None}

    if gkey in cache["marks"]:
        marks = validate_marks(cache["marks"][gkey], duration, verbose=False)
        if marks["op"] or marks["ed"]:
            log.info("  Marcas de Gemini tomadas de la caché.")
        else:
            log.info(
                "  La caché de este episodio no tiene marcas válidas; se consulta de nuevo.")

    if not (marks["op"] or marks["ed"]):
        log.info("  Consultando Gemini para detectar OP/ED...")
        try:
            raw = gemini_marks(src, duration, args.threads, args.gemini_model)
        except Exception as e:
            log.error("  Gemini falló: %s", e)
            raw = {"op": None, "ed": None}
        marks = validate_marks(raw, duration)
        if marks["op"] or marks["ed"]:
            # Solo se guarda lo válido: así nunca se reutiliza una respuesta mala
            cache["marks"][gkey] = {
                k: list(v) if v else None for k, v in marks.items()}
            save_cache(cache_path, cache)

    if marks["op"] or marks["ed"]:
        return marks, "Gemini"
    return marks, "none"


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

    log.info("Procesando: %s", rel)
    info = probe(src)
    marks, source = get_marks(src, info, args, cache, cache_path)
    if source == "none":
        log.error(
            "  Sin marcas de tiempo para %s. Se deja el archivo sin tocar.", rel)
        return False

    segs = build_segments(info["duration"], marks["op"], marks["ed"])

    def fmt(r):
        return f"{r[0]:.0f}-{r[1]:.0f} s" if r else "no tiene"
    log.info("  Marcas vía %s | OP: %s | ED: %s | %d tramos",
             source, fmt(marks["op"]), fmt(marks["ed"]), len(segs))

    processed_dir.mkdir(exist_ok=True)
    tmp_dst = dst.with_name(dst.stem + ".part.mp4")
    render(src, tmp_dst, segs, args.speed, info,
           args.threads, args.preset, args.crf)

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
    return True


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
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    in_dir = args.input.resolve()
    if not in_dir.is_dir():
        print(f"La carpeta de entrada no existe: {in_dir}")
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

    if not FFMPEG:
        log.error(
            "No encuentro ffmpeg. Pon ffmpeg.exe en %s o agrégalo al PATH.", SCRIPT_DIR)
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
        return 1

    cache_path = in_dir / "anime_x3_cache.json"
    cache = load_cache(cache_path)

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
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario.")

    log.info("Terminado. OK: %d | Fallidos/sin marcas: %d", ok, fail)
    return 0 if fail == 0 else 2

'''
if __name__ == "__main__":
    sys.exit(main())
'''
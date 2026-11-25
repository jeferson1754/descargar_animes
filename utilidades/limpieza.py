import json
import logging
import os
import re
import time
import datetime
from pathlib import Path


def ejecutar_rutina_limpieza(
    directorio_capturas="debug_screenshots",
    dias_retencion_capturas=5,
    archivos_temporales=None,
):
    """Elimina capturas de pantalla antiguas y purga archivos temporales

    residuales del ciclo de ejecución.
    """
    logging.info("🧹 Iniciando rutina de auto-limpieza del sistema...")

    # ============================================================
    # 1. LIMPIEZA DE CAPTURAS DE PANTALLA (POR ANTIGÜEDAD)
    # ============================================================
    if os.path.exists(directorio_capturas):
        ahora = time.time()
        limite_segundos = dias_retencion_capturas * 86400
        capturas_eliminadas = 0

        for archivo in os.listdir(directorio_capturas):
            ruta_archivo = os.path.join(directorio_capturas, archivo)

            if os.path.isfile(ruta_archivo):
                # Verificar tiempo de modificación del archivo
                mtime = os.path.getmtime(ruta_archivo)
                if (ahora - mtime) > limite_segundos:
                    try:
                        os.remove(ruta_archivo)
                        capturas_eliminadas += 1
                    except Exception as e:
                        logging.warning(
                            f"⚠️ No se pudo eliminar la captura {archivo}: {e}"
                        )

        if capturas_eliminadas > 0:
            logging.info(
                f"📸 Se eliminaron {capturas_eliminadas} capturas con más de {dias_retencion_capturas} días en '{directorio_capturas}'."
            )
        else:
            logging.info("📸 No hay capturas antiguas pendientes de eliminar.")
    else:
        logging.info(
            f"ℹ️ La carpeta '{directorio_capturas}' no existe. Omite paso."
        )

    # ============================================================
    # 2. LIMPIEZA / REINICIO DE ARCHIVOS TXT/JSON TEMPORALES
    # ============================================================
    if archivos_temporales is None:
        archivos_temporales = [
            "videos_tioanime.txt",
            "videos_encontrados.txt",
            "resultados_anime.txt",
            "resultados.txt"
        ]

    temporales_removidos = 0
    for temp_file in archivos_temporales:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                temporales_removidos += 1
            except Exception as e:
                logging.warning(
                    f"⚠️ No se pudo eliminar el archivo temporal {temp_file}: {e}"
                )

    if temporales_removidos > 0:
        logging.info(
            f"📄 Se purgaron {temporales_removidos} archivos temporales de ciclo."
        )

    logging.info("✅ Rutina de auto-limpieza finalizada exitosamente.")
    
_PATRON_CARPETA_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SUBCARPETAS_RECORTE = ("originales", "procesados")
_INDICE_DESCARGAS = "descargas_index.json"


def _es_subruta(base_dir: Path, candidato: Path) -> bool:
    try:
        candidato.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _candidatos_archivo(base_dir: Path, rel_str: str) -> list[Path]:
    """Genera las rutas posibles (raíz/fecha, originales y procesados) para un video."""
    limpio = rel_str.strip().replace("\\", "/").lstrip("/")
    if not limpio:
        return []
    rel = Path(limpio)
    if rel.is_absolute() or ".." in rel.parts:
        return []

    nombre = rel.name
    stem = rel.stem
    padre = rel.parent

    candidatos = [
        base_dir / padre / nombre,
        base_dir / padre / "originales" / nombre,
        base_dir / padre / "procesados" / f"{stem}.mp4",
    ]
    if padre != Path("."):
        candidatos.extend([
            base_dir / nombre,
            base_dir / "originales" / nombre,
            base_dir / "procesados" / f"{stem}.mp4",
        ])

    vistos = set()
    unicos = []
    for c in candidatos:
        if not _es_subruta(base_dir, c):
            continue
        clave = str(c).lower()
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(c)
    return unicos


def _cargar_indice_descargas(base_dir: Path) -> tuple[Path, dict]:
    indice_path = base_dir / _INDICE_DESCARGAS
    if not indice_path.is_file():
        return indice_path, {}
    try:
        datos = json.loads(indice_path.read_text(encoding="utf-8"))
        return indice_path, datos if isinstance(datos, dict) else {}
    except Exception:
        return indice_path, {}


def _guardar_indice_descargas(indice_path: Path, datos: dict) -> None:
    try:
        tmp = indice_path.with_name(indice_path.name + ".tmp_idx")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, indice_path)
    except Exception as e:
        logging.warning(f"⚠️ No se pudo actualizar {_INDICE_DESCARGAS}: {e}")


def limpiar_videos_vistos(directorio_descargas, registros_sheets, sheet_service=None):
    """
    Elimina los videos (sin procesar, en 'originales/' y en 'procesados/')
    correspondientes a episodios marcados con estado 'Visto' en Google Sheets.
    Usa la columna 'Archivo' de la hoja y, como respaldo para descargas previas,
    el índice local descargas_index.json.
    """
    if not directorio_descargas or not os.path.exists(directorio_descargas):
        logging.warning(
            f"⚠️ El directorio de descargas no existe: {directorio_descargas}"
        )
        return 0

    if not registros_sheets:
        logging.info("👁️ No hay registros de Google Sheets para revisar vistos.")
        return 0

    base_dir = Path(directorio_descargas)
    indice_path, indice = _cargar_indice_descargas(base_dir)
    indice_modificado = False

    # Mapa respaldo (nombre_lower, episodio_str) -> [rutas en indice]
    respaldo_indice = {}
    for ruta_str, info in indice.items():
        if isinstance(info, dict):
            clave = (
                str(info.get("nombre", "")).strip().lower(),
                str(info.get("episodio", "")).strip(),
            )
            respaldo_indice.setdefault(clave, []).append(ruta_str)

    logging.info(
        f"👁️ Verificando videos de animes 'Visto' para eliminar en: {directorio_descargas}"
    )

    videos_eliminados = 0
    espacio_liberado_bytes = 0

    for item in registros_sheets:
        if str(item.get("estado", "")).strip().lower() != "visto":
            continue

        nombre = str(item.get("nombre", "")).strip()
        episodio = str(item.get("episodio", "")).strip()
        archivo_rel = str(item.get("archivo", "")).strip()

        if archivo_rel.lower().startswith("[eliminado]"):
            continue

        candidatos = []
        if archivo_rel:
            candidatos = _candidatos_archivo(base_dir, archivo_rel)
        else:
            for ruta_abs in respaldo_indice.get((nombre.lower(), episodio), []):
                p = Path(ruta_abs)
                try:
                    rel = p.resolve().relative_to(base_dir.resolve())
                    candidatos.extend(_candidatos_archivo(base_dir, rel.as_posix()))
                except ValueError:
                    if p.is_file() and _es_subruta(base_dir, p):
                        candidatos.append(p)

        eliminados_este_ep = 0
        for ruta in candidatos:
            if ruta.is_file():
                try:
                    tamano = ruta.stat().st_size
                    ruta.unlink()
                    videos_eliminados += 1
                    eliminados_este_ep += 1
                    espacio_liberado_bytes += tamano
                    logging.info(f"🗑️ Video eliminado (Visto): {ruta.relative_to(base_dir)}")
                except Exception as e:
                    logging.warning(f"⚠️ No se pudo eliminar {ruta}: {e}")

        if eliminados_este_ep > 0:
            # Limpiar referencias en descargas_index.json si existían
            for k in list(indice):
                info = indice.get(k)
                if isinstance(info, dict) and (
                    str(info.get("nombre", "")).strip().lower() == nombre.lower()
                    and str(info.get("episodio", "")).strip() == episodio
                ):
                    indice.pop(k, None)
                    indice_modificado = True

            if sheet_service and archivo_rel:
                try:
                    from base_excel import actualizar_estado_google_sheets

                    actualizar_estado_google_sheets(
                        sheet_service=sheet_service,
                        nombre_hoja="Animes",
                        nombre_anime=nombre,
                        episodio=episodio,
                        nuevo_estado="Visto",
                        archivo=f"[Eliminado] {archivo_rel}",
                    )
                except Exception as e:
                    logging.warning(
                        f"⚠️ No se pudo marcar '[Eliminado]' en Sheets para {nombre} Ep {episodio}: {e}"
                    )

    if indice_modificado:
        _guardar_indice_descargas(indice_path, indice)

    if videos_eliminados > 0:
        espacio_mb = espacio_liberado_bytes / (1024 * 1024)
        logging.info(
            f"🧹 Limpieza de vistos finalizada: {videos_eliminados} archivo(s) eliminado(s) "
            f"({espacio_mb:.2f} MB liberados)."
        )
    else:
        logging.info("👁️ No hay videos vistos pendientes de eliminación.")

    return videos_eliminados


def limpiar_carpetas_fechas_vacias(directorio_base):
    """Elimina subcarpetas de fecha (YYYY-MM-DD) y de recorte que hayan quedado vacías."""
    if not os.path.exists(directorio_base):
        return

    for raiz, dirs, _ in os.walk(directorio_base, topdown=False):
        for d in dirs:
            if d.startswith("."):
                continue  # evita carpetas de sincronización como .tmp.driveupload
            if not (_PATRON_CARPETA_FECHA.match(d) or d.lower() in _SUBCARPETAS_RECORTE):
                continue
            ruta_carpeta = os.path.join(raiz, d)
            if not os.listdir(ruta_carpeta):
                try:
                    os.rmdir(ruta_carpeta)
                    logging.info(f"📂 Carpeta vacía eliminada: {d}")
                except Exception as e:
                    logging.warning(
                        f"⚠️ No se pudo eliminar la carpeta {d}: {e}"
                    )
        
def obtener_directorio_fecha(directorio_base):
    """Crea y retorna una subcarpeta dentro de 'directorio_base' basada en la

    fecha actual (YYYY-MM-DD).
    """
    # Formato de la carpeta: '2026-10-21'
    fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
    ruta_fecha = os.path.join(directorio_base, fecha_hoy)

    if not os.path.exists(ruta_fecha):
        os.makedirs(ruta_fecha, exist_ok=True)
        logging.info(f"📁 Subcarpeta del día creada: {ruta_fecha}")

    return ruta_fecha
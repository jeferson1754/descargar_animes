import os
import shutil


def mover_videos_a_directorio(directorio_origen, directorio_destino):
    """
    Busca videos en todas las subcarpetas de 'directorio_origen' 
    y los mueve a 'directorio_destino'.
    """
    # Extensiones de video a buscar

    extensiones_video = ('.mp4', '.mkv', '.avi', '.mov', '.wmv')

    # Crear el directorio de destino si no existe
    if not os.path.exists(directorio_destino):
        os.makedirs(directorio_destino)
        print(f"Directorio de destino creado: {directorio_destino}")

    contador = 0

    # Recorrer el directorio origen
    for root, dirs, files in os.walk(directorio_origen):
        # Evitamos mover archivos que ya están en el directorio destino
        if os.path.abspath(root) == os.path.abspath(directorio_destino):
            continue

        for file in files:
            if file.lower().endswith(extensiones_video):
                archivo_origen = os.path.join(root, file)
                archivo_destino = os.path.join(directorio_destino, file)

                # Evitar sobrescribir si el archivo ya existe
                if os.path.exists(archivo_destino):
                    print(
                        f"⚠️ El archivo ya existe en destino, saltando: {file}")
                    continue

                try:
                    shutil.move(archivo_origen, archivo_destino)
                    print(f"✅ Movido: {file}")
                    contador += 1
                except Exception as e:
                    print(f"❌ Error al mover {file}: {e}")

    print(f"\nProceso finalizado. Se movieron {contador} archivos.")

# --- Ejemplo de uso ---
origen = r"C:\Users\jvargas\Phyton\Descargar_Animes\descargas"
mover_videos_a_directorio(origen, origen)

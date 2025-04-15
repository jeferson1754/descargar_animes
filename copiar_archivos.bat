@echo off
setlocal

:: Definir carpetas de origen y destino
set "ORIGEN=C:\xampp-2\htdocs\Proyecto_BaseFoto\Diseños"
set "DESTINO=\\192.168.111.34\AntiVirus\cORREO"

:: Crear la carpeta de destino si no existe
if not exist "%DESTINO%" mkdir "%DESTINO%"

:: Copiar solo los archivos nuevos o que no existen en destino
xcopy "%ORIGEN%\*" "%DESTINO%\" /E /I /D

echo Archivos copiados correctamente.
pause

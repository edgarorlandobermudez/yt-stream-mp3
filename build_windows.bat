@echo off
REM ================================================================
REM  build_windows.bat — Genera el .exe de yt-stream-mp3 en Windows
REM  Requisito: Python 3.10+ instalado y en el PATH
REM ================================================================

echo.
echo ================================================
echo   Construyendo yt-stream-mp3.exe para Windows
echo ================================================
echo.

REM Instalar dependencias
echo [1/3] Instalando dependencias...
pip install -r requirements.txt pyinstaller
if errorlevel 1 ( echo ERROR: fallo pip install & pause & exit /b 1 )

REM Limpiar builds anteriores
echo [2/3] Limpiando builds anteriores...
if exist dist\yt-stream-mp3.exe del /f dist\yt-stream-mp3.exe
if exist build rmdir /s /q build

REM Compilar
echo [3/3] Compilando con PyInstaller...
pyinstaller yt_mp3.spec
if errorlevel 1 ( echo ERROR: fallo PyInstaller & pause & exit /b 1 )

echo.
echo ================================================
echo  LISTO!
echo  El ejecutable esta en:  dist\yt-stream-mp3.exe
echo ================================================
pause

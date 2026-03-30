#!/usr/bin/env bash
# ================================================================
#  build_linux_mac.sh — Genera el binario nativo (Linux o macOS)
#  Uso: bash build_linux_mac.sh
# ================================================================
set -e

echo ""
echo "================================================"
echo "  Construyendo yt-stream-mp3 (Linux / macOS)"
echo "================================================"
echo ""

echo "[1/3] Instalando dependencias..."
pip install -r requirements.txt pyinstaller

echo "[2/3] Limpiando builds anteriores..."
rm -rf build dist/yt-stream-mp3

echo "[3/3] Compilando con PyInstaller..."
pyinstaller yt_mp3.spec

echo ""
echo "================================================"
echo " LISTO!"
echo " El ejecutable está en:  dist/yt-stream-mp3"
echo " Ejecutar con:           ./dist/yt-stream-mp3"
echo "================================================"

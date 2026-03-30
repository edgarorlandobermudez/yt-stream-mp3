# yt_mp3.spec — PyInstaller spec para generar el .exe
# Ejecutar en Windows con: pyinstaller yt_mp3.spec

import sys
from pathlib import Path

# Rutas de datos de paquetes
import customtkinter
import static_ffmpeg

CTK_PATH = str(Path(customtkinter.__file__).parent)
SF_PATH  = str(Path(static_ffmpeg.__file__).parent)

block_cipher = None

a = Analysis(
    ["gui.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # CustomTkinter: temas, fuentes, imágenes
        (CTK_PATH, "customtkinter"),
        # static_ffmpeg: binarios de ffmpeg
        (SF_PATH, "static_ffmpeg"),
        # Plantillas de la web (por si acaso)
        ("templates", "templates"),
        ("static",    "static"),
    ],
    hiddenimports=[
        "yt_dlp",
        "yt_mp3",
        "mutagen",
        "mutagen.id3",
        "static_ffmpeg",
        "customtkinter",
        "PIL",
        "PIL._tkinter_finder",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="yt-stream-mp3",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Sin ventana de consola (solo GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",      # Descomenta si tienes un ícono .ico
)

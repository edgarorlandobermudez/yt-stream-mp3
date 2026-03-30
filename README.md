# 🎵 yt-stream-mp3

Descargador de audio en formato **MP3** desde YouTube, usando Python y `yt-dlp`.

---

## 📋 Requisitos

| Dependencia | Instalación |
|-------------|-------------|
| Python 3.10+ | [python.org](https://www.python.org/) |
| `yt-dlp` | `pip install -r requirements.txt` |
| `static-ffmpeg` | `pip install -r requirements.txt` (incluye ffmpeg automáticamente) |

> **No necesitas instalar ffmpeg manualmente.** El paquete `static-ffmpeg` lo descarga e integra automáticamente.

---

## 🚀 Instalación

```bash
# 1. Clona o descarga el proyecto
git clone <URL-del-repo>
cd yt-stream-mp3

# 2. Instala las dependencias de Python
pip install -r requirements.txt
```

---

## 🖥️ Interfaz Web (recomendado)

La interfaz web funciona en **cualquier dispositivo** con navegador: Linux, Windows, Mac, Android, iOS.

```bash
python3 app.py
```

Luego abre en tu navegador:
- **Mismo equipo:** http://localhost:5000
- **Otro dispositivo en la misma red (celular, tablet):** `http://<IP-LOCAL>:5000`

> La IP local se muestra en la consola al iniciar la app.

### Funciones de la interfaz:
- Pegar URL de YouTube (video o playlist)
- Seleccionar calidad de audio
- Limitar número de canciones de playlist
- Barra de progreso en tiempo real
- Lista de archivos descargados con botón **⬇ Guardar**

---

## ⌨️ Uso por línea de comandos (opcional)

### Video individual

```bash
python3 yt_mp3.py https://www.youtube.com/watch?v=WcIcVapfqXw
```

### Playlist completa (crea subcarpeta automática)

```bash
python3 yt_mp3.py "https://www.youtube.com/playlist?list=PLxxxxxx"
```

### Radio Mix / Auto-playlist de YouTube

```bash
python3 yt_mp3.py "https://www.youtube.com/watch?v=LzInU71ljJQ&list=RDLzInU71ljJQ"
```

### Solo las primeras N canciones de una playlist

```bash
python3 yt_mp3.py --limit 10 "https://www.youtube.com/playlist?list=PLxxxxxx"
```

### Con directorio de salida y calidad máxima

```bash
python3 yt_mp3.py -q 320 -o ~/Musica "https://www.youtube.com/playlist?list=PLxxxxxx"
```

### Múltiples URLs a la vez

```bash
python3 yt_mp3.py https://youtu.be/VIDEO1 https://youtu.be/VIDEO2
```

### Sin crear subcarpeta por playlist

```bash
python3 yt_mp3.py --no-playlist-folder "https://www.youtube.com/playlist?list=PLxxxxxx"
```

---

## ⚙️ Opciones

| Flag | Descripción | Valor por defecto |
|------|-------------|-------------------|
| `URL` | Una o más URLs de YouTube | — |
| `-o`, `--output` | Directorio base donde se guardan los MP3 | `./descargas` |
| `-q`, `--quality` | Calidad en kbps: `64`, `128`, `192`, `256`, `320` | `192` |
| `--limit N` | Descargar solo las primeras N canciones de una playlist | sin límite |
| `--no-playlist-folder` | No crear subcarpeta por playlist | subcarpeta activada |
| `-h`, `--help` | Muestra la ayuda | — |

## 📦 Compilar ejecutable (.exe / binario)

Genera un archivo ejecutable que **no requiere tener Python instalado**.

### Windows → `.exe`

1. Instala [Python 3.10+](https://www.python.org/) en Windows
2. Copia la carpeta del proyecto al PC con Windows
3. Doble clic en **`build_windows.bat`**
4. El `.exe` se genera en `dist\yt-stream-mp3.exe`

```bat
build_windows.bat
```

### Linux / macOS → binario nativo

```bash
bash build_linux_mac.sh
# El binario queda en:  dist/yt-stream-mp3
./dist/yt-stream-mp3
```

> **Nota:** el ejecutable es de \~170 MB porque incluye Python, ffmpeg y todas las dependencias embebidas. No necesita instalación.

---



```
yt-stream-mp3/
├── yt_mp3.py          # Script principal
├── requirements.txt   # Dependencias Python
└── README.md          # Esta documentación
```

---

## 📦 Dependencias

- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — Descargador de videos/audio de YouTube y más de 1000 sitios.
- [`ffmpeg`](https://ffmpeg.org/) — Herramienta de sistema para convertir el audio a MP3.

---

## ⚠️ Notas

- Los archivos MP3 se guardan con el **título del video** como nombre de archivo.
- Si `ffmpeg` no está instalado, la conversión a MP3 **no funcionará**.
- Respetar los términos de uso de YouTube. Usar solo para contenido con licencia libre o de uso personal.

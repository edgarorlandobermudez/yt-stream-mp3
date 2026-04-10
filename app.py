#!/usr/bin/env python3
"""
app.py — Interfaz web para yt_mp3.py
Funciona en cualquier dispositivo con navegador (Linux, Windows, Mac, Android, iOS).
Iniciar con:  python3 app.py
Luego abrir:  http://localhost:5000
              http://<IP-LOCAL>:5000  (desde otro dispositivo en la misma red)
"""

import re
import threading
from pathlib import Path

from flask import Flask, render_template, send_from_directory, jsonify, request, abort
from flask_socketio import SocketIO, emit

# Importar helpers de yt_mp3
from yt_mp3 import (
    _cleanup_temp_source_files,
    _parse_artist_title,
    _safe_filename,
    _write_id3_tags,
    _TITLE_NOISE,
)
import yt_dlp

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

DOWNLOADS_DIR = Path(__file__).parent / "descargas"
DOWNLOADS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "yt-mp3-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Bloqueo simple para evitar descargas simultáneas
_download_lock = threading.Lock()
_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Rutas Flask
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/files")
def list_files():
    """Lista todos los MP3 disponibles (recursivo)."""
    files = []
    for mp3 in sorted(DOWNLOADS_DIR.rglob("*.mp3")):
        rel = mp3.relative_to(DOWNLOADS_DIR)
        files.append({
            "name": mp3.name,
            "path": str(rel),
            "folder": str(rel.parent) if rel.parent != Path(".") else "",
            "size_mb": round(mp3.stat().st_size / 1_048_576, 1),
        })
    return jsonify(files)


@app.route("/files/clear", methods=["POST"])
def clear_files():
    """Elimina todos los MP3 descargados (recursivo)."""
    removed = 0
    errors = 0
    for mp3 in DOWNLOADS_DIR.rglob("*.mp3"):
        try:
            mp3.unlink()
            removed += 1
        except OSError:
            errors += 1

    return jsonify({"removed": removed, "errors": errors})


@app.route("/files/delete", methods=["POST"])
def delete_file():
    """Elimina un MP3 específico por ruta relativa dentro de descargas."""
    data = request.get_json(silent=True) or {}
    rel_path = (data.get("path") or "").strip()
    if not rel_path:
        return jsonify({"error": "path requerido"}), 400

    target = Path(rel_path)
    if (
        ".." in target.parts
        or target.is_absolute()
        or target.suffix.lower() != ".mp3"
    ):
        return jsonify({"error": "path inválido"}), 400

    full_path = DOWNLOADS_DIR / target
    if not full_path.exists():
        return jsonify({"error": "archivo no encontrado"}), 404

    try:
        full_path.unlink()
    except OSError:
        return jsonify({"error": "no se pudo eliminar"}), 500

    return jsonify({"deleted": rel_path})


@app.route("/download/stop", methods=["POST"])
def stop_download_http():
    """Solicita detener la descarga activa."""
    _stop_event.set()
    return jsonify({"stopping": True})


@app.route("/download/<path:filepath>")
def download_file(filepath):
    """Sirve el MP3 para descarga."""
    safe = Path(filepath)
    if ".." in safe.parts:
        abort(400)
    return send_from_directory(
        DOWNLOADS_DIR,
        str(safe),
        as_attachment=True,
        mimetype="audio/mpeg",
    )


# ---------------------------------------------------------------------------
# SocketIO — descarga con progreso en tiempo real
# ---------------------------------------------------------------------------

@socketio.on("start_download")
def handle_download(data: dict):
    url = (data.get("url") or "").strip()
    quality = data.get("quality", "192")
    limit = int(data.get("limit") or 0) or None
    playlist_folder = bool(data.get("playlist_folder", True))
    full_playlist = bool(data.get("full_playlist", True))

    if not url:
        emit("error", {"msg": "URL vacía."})
        return

    if not _download_lock.acquire(blocking=False):
        emit("error", {"msg": "Ya hay una descarga en progreso. Espera a que termine."})
        return

    stopped = False
    _stop_event.clear()
    try:
        stopped = _run_download(
            url,
            quality,
            limit,
            playlist_folder,
            full_playlist,
        )
    except Exception as exc:  # pragma: no cover - error inesperado en runtime
        emit("error", {"msg": f"Error inesperado: {exc}"})
    finally:
        _download_lock.release()
        emit("done", {"stopped": bool(stopped)})


@socketio.on("stop_download")
def handle_stop_download():
    """Marca la descarga actual para detenerse."""
    _stop_event.set()


def _emit(event: str, data: dict):
    socketio.emit(event, data)


def _count_playlist(url: str) -> int:
    opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True}

    def _count_match_filter(_info, *, incomplete=False):
        if _stop_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Detenida por el usuario")
        return None

    opts["match_filter"] = _count_match_filter

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
        return len(info.get("entries") or [])


def _run_download(
    url: str,
    quality: str,
    limit: int | None,
    playlist_folder: bool,
    full_playlist: bool,
):
    if _stop_event.is_set():
        _emit("log", {"msg": "⏹ Descarga detenida por el usuario"})
        return True

    _emit("log", {"msg": f"🔍 Analizando URL…"})

    if full_playlist:
        try:
            total = _count_playlist(url)
        except yt_dlp.utils.DownloadCancelled:
            _emit("log", {"msg": "⏹ Descarga detenida por el usuario"})
            return True

        is_playlist = total > 1
        effective = min(total, limit) if (limit and total) else (total or 1)
    else:
        total = 1
        is_playlist = False
        effective = 1

    if is_playlist:
        suffix = " (limitado)" if limit and limit < total else ""
        _emit("log", {"msg": f"📋 Playlist: {effective} canciones{suffix}"})
    else:
        _emit("log", {"msg": "🎵 Video individual detectado"})
        if not full_playlist:
            _emit("log", {"msg": "🔢 Modo índice: solo se descargará el video del enlace"})

    _emit("progress_init", {"total": effective})

    current: dict = {"index": 0, "last_file": None}

    def progress_hook(d: dict):
        if _stop_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Detenida por el usuario")

        if d["status"] == "downloading":
            fname = d.get("filename")
            if fname and fname != current["last_file"]:
                current["last_file"] = fname
                current["index"] += 1
                _emit("track_start", {"index": current["index"], "total": effective})

            downloaded = d.get("downloaded_bytes", 0)
            total_b = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed = d.get("speed") or 0
            if total_b:
                pct = round(downloaded / total_b * 100, 1)
                speed_kb = round(speed / 1024, 1)
                _emit("progress", {"pct": pct, "speed_kb": speed_kb,
                                   "index": current["index"], "total": effective})

        elif d["status"] == "finished":
            _emit("log", {"msg": "  ✅ Convirtiendo a MP3…"})

    outtmpl = str(DOWNLOADS_DIR / "%(id)s.%(ext)s")
    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    def _match_filter(_info, *, incomplete=False):
        if _stop_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Detenida por el usuario")
        return None

    opts["match_filter"] = _match_filter

    if limit:
        opts["playlistend"] = limit
    if not full_playlist:
        opts["noplaylist"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}
    except yt_dlp.utils.DownloadCancelled:
        _emit("log", {"msg": "⏹ Descarga detenida por el usuario"})
        return True
    except yt_dlp.utils.DownloadError as exc:
        _emit("error", {"msg": str(exc)})
        return False

    entries = info.get("entries") if is_playlist else [info]
    entries = [e for e in (entries or []) if e]

    ok = 0
    for idx, entry in enumerate(entries, start=1):
        if _stop_event.is_set():
            _emit("log", {"msg": "⏹ Descarga detenida por el usuario"})
            return True

        video_id = entry.get("id", "")
        tmp_mp3 = DOWNLOADS_DIR / f"{video_id}.mp3"
        if not tmp_mp3.exists():
            continue

        if is_playlist and playlist_folder:
            folder_name = _safe_filename(
                info.get("title") or info.get("playlist_title") or "Playlist"
            )
            dest_dir = DOWNLOADS_DIR / folder_name
            dest_dir.mkdir(exist_ok=True)
        else:
            dest_dir = DOWNLOADS_DIR

        artist, title = _parse_artist_title(entry)
        filename = _safe_filename(f"{artist} - {title}.mp3")
        new_path = dest_dir / filename

        counter = 1
        while new_path.exists() and new_path != tmp_mp3:
            new_path = dest_dir / _safe_filename(f"{artist} - {title} ({counter}).mp3")
            counter += 1

        tmp_mp3.rename(new_path)
        _write_id3_tags(new_path, entry, idx if is_playlist else None)
        _cleanup_temp_source_files(DOWNLOADS_DIR, video_id)

        rel_path = str(new_path.relative_to(DOWNLOADS_DIR))
        _emit("track_done", {
            "index": idx,
            "total": effective,
            "artist": artist,
            "title": title,
            "path": rel_path,
            "size_mb": round(new_path.stat().st_size / 1_048_576, 1),
        })
        ok += 1

    msg = (f"🎉 Playlist completa: {ok}/{effective} canciones"
           if is_playlist else f"🎧 Descarga completada: {ok} archivo(s)")
    _emit("log", {"msg": msg})
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import socket

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"

    print("=" * 55)
    print("  🎵  yt-stream-mp3  |  Interfaz Web")
    print("=" * 55)
    print(f"  Local  :  http://localhost:5000")
    print(f"  Red    :  http://{local_ip}:5000")
    print("  (abre cualquiera de estas URLs en tu navegador)")
    print("=" * 55)

    socketio.run(app, host="0.0.0.0", port=5000, debug=False)

#!/usr/bin/env python3
"""
yt_mp3.py — Descargador de audio MP3 desde YouTube
Filenames: Artista - Canción.mp3
ID3 tags:  title, artist, album, track, year
Instalar dependencias:
    pip install -r requirements.txt
"""

import re
import sys
import argparse
from pathlib import Path

import yt_dlp
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TDRC, APIC
from mutagen.id3 import ID3NoHeaderError

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# Sufijos comunes en títulos de YouTube que no forman parte del nombre real
_TITLE_NOISE = re.compile(
    r"\s*[\(\[\|]?\s*"
    r"(official\s*(music\s*)?video|official\s*audio|official\s*lyric\s*video"
    r"|lyrics?\s*video|lyric\s*video|lyrics|live\s*(in|at|@)[^)\]]*"
    r"|hd|hq|4k|remaster(ed)?|explicit|radio\s*edit|feat\.?[^)\]]*"
    r"|video\s*oficial|audio\s*oficial|videoclip\s*oficial)"
    r"\s*[\)\]]?\s*$",
    re.IGNORECASE,
)

_current_track: dict = {"index": 0, "total": 0}


# ---------------------------------------------------------------------------
# Helpers de metadata
# ---------------------------------------------------------------------------

def _clean_title(raw: str) -> str:
    """Elimina sufijos de marketing del título."""
    return _TITLE_NOISE.sub("", raw).strip(" -–—|")


def _parse_artist_title(info: dict) -> tuple[str, str]:
    """
    Extrae (artista, título) del info dict de yt-dlp.
    Prioridad:
      1. Campos 'artist' y 'track' (YouTube Music)
      2. Si el título tiene formato 'Artista - Canción', lo parte
      3. Fallback: uploader como artista, título limpio
    """
    raw_title = info.get("fulltitle") or info.get("title") or "Desconocido"

    # YouTube Music / videos con metadatos explícitos
    if info.get("artist") and info.get("track"):
        return info["artist"], _clean_title(info["track"])

    # Patrón "Artista - Canción" en el título (muy común en YouTube)
    match = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", raw_title)
    if match:
        artist = match.group(1).strip()
        title = _clean_title(match.group(2).strip())
        return artist, title

    # Fallback
    artist = info.get("uploader") or info.get("channel") or "Desconocido"
    return artist, _clean_title(raw_title)


def _safe_filename(name: str) -> str:
    """Elimina caracteres no válidos en nombres de archivo."""
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()


def _write_id3_tags(mp3_path: Path, info: dict, playlist_index: int | None = None) -> None:
    """Escribe tags ID3 correctos en el MP3 usando mutagen."""
    artist, title = _parse_artist_title(info)
    album = (
        info.get("album")
        or info.get("playlist_title")
        or info.get("uploader")
        or artist
    )
    year = (info.get("upload_date") or "")[:4]

    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()

    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags["TPE1"] = TPE1(encoding=3, text=artist)
    tags["TALB"] = TALB(encoding=3, text=album)
    if year:
        tags["TDRC"] = TDRC(encoding=3, text=year)
    if playlist_index is not None:
        total = _current_track["total"]
        tags["TRCK"] = TRCK(encoding=3, text=f"{playlist_index}/{total}" if total else str(playlist_index))
    else:
        # Elimina TRCK espurio que puede insertar FFmpegMetadata
        tags.delall("TRCK")

    tags.save(str(mp3_path))


# ---------------------------------------------------------------------------
# yt-dlp hooks y opciones
# ---------------------------------------------------------------------------

def _progress_hook(d: dict) -> None:
    if d["status"] == "downloading":
        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        speed = d.get("speed") or 0
        idx = _current_track["index"]
        tot = _current_track["total"]
        track_info = f"[{idx}/{tot}] " if tot else ""
        if total:
            pct = downloaded / total * 100
            speed_kb = speed / 1024
            print(
                f"\r  ⬇  {track_info}{pct:5.1f}%  —  {speed_kb:6.1f} KB/s",
                end="",
                flush=True,
            )
    elif d["status"] == "finished":
        print("\n  ✅  Descarga completa → convirtiendo a MP3…")


def build_ydl_opts(output_dir: Path, audio_quality: str, limit: int | None) -> dict:
    # Usamos %(id)s como nombre temporal para renombrar después con el nombre correcto
    template = str(output_dir / "%(id)s.%(ext)s")
    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_quality,
            },
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
        "progress_hooks": [_progress_hook],
        "quiet": False,
        "no_warnings": False,
        "ignoreerrors": True,
        "extract_flat": False,
    }
    if limit:
        opts["playlistend"] = limit
    return opts


# ---------------------------------------------------------------------------
# Descarga y post-procesado
# ---------------------------------------------------------------------------

def _count_playlist(url: str) -> int:
    opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
        return len(info.get("entries") or [])


def _rename_and_tag(
    mp3_path: Path,
    dest_dir: Path,
    info: dict,
    playlist_index: int | None,
) -> Path:
    """Renombra el MP3 a 'Artista - Canción.mp3' y escribe los ID3 tags."""
    artist, title = _parse_artist_title(info)
    filename = _safe_filename(f"{artist} - {title}.mp3")
    new_path = dest_dir / filename

    # Si existe, añade sufijo numérico para no sobrescribir
    counter = 1
    while new_path.exists() and new_path != mp3_path:
        new_path = dest_dir / _safe_filename(f"{artist} - {title} ({counter}).mp3")
        counter += 1

    mp3_path.rename(new_path)
    _write_id3_tags(new_path, info, playlist_index)
    return new_path


def _cleanup_temp_source_files(output_dir: Path, video_id: str) -> None:
    """Elimina archivos temporales del id descargado (ej. .webm, .m4a)."""
    if not video_id:
        return

    removable_suffixes = {
        ".webm",
        ".m4a",
        ".mp4",
        ".opus",
        ".part",
        ".temp",
    }

    for temp_file in output_dir.glob(f"{video_id}.*"):
        if temp_file.suffix.lower() in removable_suffixes:
            try:
                temp_file.unlink()
            except OSError:
                # No interrumpir el flujo si no se puede borrar un temporal.
                pass


def download(
    urls: list[str],
    output_dir: Path,
    audio_quality: str,
    playlist_folder: bool,
    limit: int | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for url in urls:
        print(f"\n🔍  Analizando: {url}")

        total = _count_playlist(url)
        is_playlist = total > 1
        effective = min(total, limit) if (limit and total) else total or 1

        if is_playlist:
            print(f"📋  Playlist detectada: {effective} canciones"
                  + (" (limitado)" if limit and limit < total else ""))

        _current_track["total"] = effective
        _current_track["index"] = 0

        opts = build_ydl_opts(output_dir, audio_quality, limit)

        # Hook para contar pistas
        orig_hook = opts["progress_hooks"][0]
        _last_file: dict = {"name": None}

        def _counting_hook(d: dict, _h=orig_hook, _lf=_last_file) -> None:
            if d["status"] == "downloading":
                fname = d.get("filename")
                if fname and fname != _lf["name"]:
                    _lf["name"] = fname
                    _current_track["index"] += 1
            _h(d)

        opts["progress_hooks"] = [_counting_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
        except yt_dlp.utils.DownloadError as exc:
            print(f"  ❌  Error: {exc}", file=sys.stderr)
            continue

        # Determinar lista de entradas descargadas
        entries = info.get("entries") if is_playlist else [info]
        entries = [e for e in (entries or []) if e]

        ok = 0
        for idx, entry in enumerate(entries, start=1):
            video_id = entry.get("id", "")
            tmp_mp3 = output_dir / f"{video_id}.mp3"

            if not tmp_mp3.exists():
                continue

            # Subcarpeta por playlist
            if is_playlist and playlist_folder:
                playlist_name = _safe_filename(
                    info.get("title") or info.get("playlist_title") or "Playlist"
                )
                dest_dir = output_dir / playlist_name
                dest_dir.mkdir(exist_ok=True)
            else:
                dest_dir = output_dir

            _rename_and_tag(
                tmp_mp3,
                dest_dir,
                entry,
                idx if is_playlist else None,
            )
            _cleanup_temp_source_files(output_dir, video_id)
            artist, title = _parse_artist_title(entry)
            print(f"  🎧  [{idx}/{effective}] {artist} - {title}.mp3")
            ok += 1

        if is_playlist:
            print(f"\n✔  Playlist: {ok}/{effective} canciones descargadas")
        else:
            if ok == 0:
                print("  ❌  No se encontró el archivo MP3 generado", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga audio de YouTube en MP3 con nombre y tags correctos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python yt_mp3.py https://www.youtube.com/watch?v=WcIcVapfqXw
  python yt_mp3.py "https://www.youtube.com/watch?v=LzInU71ljJQ&list=RDLzInU71ljJQ"
  python yt_mp3.py --limit 10 -q 320 -o ~/Musica "https://www.youtube.com/playlist?list=PLxxx"
        """,
    )
    parser.add_argument("urls", nargs="+", metavar="URL",
                        help="Una o más URLs de YouTube (videos o playlists).")
    parser.add_argument("-o", "--output", default="descargas", metavar="DIR",
                        help="Directorio base de salida (default: ./descargas).")
    parser.add_argument("-q", "--quality", default="192",
                        choices=["64", "128", "192", "256", "320"], metavar="KBPS",
                        help="Calidad en kbps (default: 192).")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Descargar solo las primeras N canciones de una playlist.")
    parser.add_argument("--no-playlist-folder", action="store_true",
                        help="No crear subcarpeta por playlist.")

    args = parser.parse_args()
    output_dir = Path(args.output).expanduser().resolve()

    print(f"📂  Destino  : {output_dir}")
    print(f"🎚   Calidad  : {args.quality} kbps")
    if args.limit:
        print(f"🔢  Límite   : {args.limit} canciones")
    print(f"🔗  URLs     : {len(args.urls)}")

    download(
        args.urls,
        output_dir,
        args.quality,
        playlist_folder=not args.no_playlist_folder,
        limit=args.limit,
    )
    print("\n✔  ¡Listo!")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
gui.py — Interfaz gráfica para yt-stream-mp3
Requiere:  pip install customtkinter
Ejecutar:  python3 gui.py
"""

import threading
import subprocess
import sys
import os
from pathlib import Path
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Motor de descarga
from yt_mp3 import _parse_artist_title, _safe_filename, _write_id3_tags
import yt_dlp

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuración visual
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT   = "#e53935"
ACCENT2  = "#ff6f61"
BG       = "#0f0f12"
SURFACE  = "#1a1a22"
CARD     = "#22222e"
BORDER   = "#2e2e3e"
TEXT     = "#f0f0f5"
MUTED    = "#8888aa"
GREEN    = "#4caf7d"

DOWNLOADS_DEFAULT = Path(__file__).parent / "descargas"


# ---------------------------------------------------------------------------
# Lógica de descarga (hilo separado)
# ---------------------------------------------------------------------------

def _count_playlist(url: str) -> int:
    opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
        return len(info.get("entries") or [])


def run_download(url, quality, limit, playlist_folder, output_dir,
                 on_log, on_progress, on_track_done, on_finish):
    """Ejecuta la descarga en un hilo separado y envía callbacks a la GUI."""
    try:
        on_log(f"🔍 Analizando URL…")
        total = _count_playlist(url)
        is_playlist = total > 1
        effective = min(total, limit) if (limit and total) else (total or 1)

        if is_playlist:
            suffix = " (limitado)" if limit and limit < total else ""
            on_log(f"📋 Playlist: {effective} canciones{suffix}")
        else:
            on_log("🎵 Video individual detectado")

        current = {"index": 0, "last_file": None}

        def progress_hook(d):
            if d["status"] == "downloading":
                fname = d.get("filename")
                if fname and fname != current["last_file"]:
                    current["last_file"] = fname
                    current["index"] += 1
                    on_log(f"⬇  [{current['index']}/{effective}] descargando…")

                downloaded = d.get("downloaded_bytes", 0)
                total_b = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                speed = d.get("speed") or 0
                if total_b:
                    pct = downloaded / total_b * 100
                    speed_kb = speed / 1024
                    # Progreso global: pista actual + fracción interna
                    global_pct = ((current["index"] - 1) / effective * 100
                                  + pct / effective)
                    on_progress(global_pct, current["index"], effective, speed_kb)
            elif d["status"] == "finished":
                on_log("  ✅ Convirtiendo a MP3…")

        outtmpl = str(output_dir / "%(id)s.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {"key": "FFmpegExtractAudio",
                 "preferredcodec": "mp3", "preferredquality": quality},
                {"key": "FFmpegMetadata", "add_metadata": True},
            ],
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        if limit:
            opts["playlistend"] = limit

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}

        entries = info.get("entries") if is_playlist else [info]
        entries = [e for e in (entries or []) if e]

        ok = 0
        for idx, entry in enumerate(entries, start=1):
            video_id = entry.get("id", "")
            tmp_mp3 = output_dir / f"{video_id}.mp3"
            if not tmp_mp3.exists():
                continue

            if is_playlist and playlist_folder:
                folder_name = _safe_filename(
                    info.get("title") or info.get("playlist_title") or "Playlist")
                dest_dir = output_dir / folder_name
                dest_dir.mkdir(exist_ok=True)
            else:
                dest_dir = output_dir

            artist, title = _parse_artist_title(entry)
            filename = _safe_filename(f"{artist} - {title}.mp3")
            new_path = dest_dir / filename
            counter = 1
            while new_path.exists() and new_path != tmp_mp3:
                new_path = dest_dir / _safe_filename(f"{artist} - {title} ({counter}).mp3")
                counter += 1

            tmp_mp3.rename(new_path)
            _write_id3_tags(new_path, entry, idx if is_playlist else None)

            size_mb = round(new_path.stat().st_size / 1_048_576, 1)
            on_track_done(artist, title, size_mb, str(new_path))
            ok += 1

        msg = (f"🎉 Listo: {ok}/{effective} canciones"
               if is_playlist else "🎧 Descarga completada")
        on_log(msg)
        on_finish(ok)

    except Exception as exc:
        on_log(f"❌ Error: {exc}")
        on_finish(0)


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🎵 yt-stream-mp3")
        self.geometry("720x780")
        self.minsize(560, 600)
        self.configure(fg_color=BG)

        self._output_dir = DOWNLOADS_DEFAULT
        self._output_dir.mkdir(exist_ok=True)
        self._downloading = False
        self._files: list[dict] = []

        self._build_ui()
        self._load_files()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # ── Header ──────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=24, pady=(20, 4), sticky="ew")
        ctk.CTkLabel(hdr, text="🎵 yt-stream-mp3",
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(hdr, text="Descargador de MP3",
                     font=ctk.CTkFont(size=13), text_color=MUTED).pack(
                         side="left", padx=(12, 0), pady=(6, 0))

        # ── Form card ───────────────────────────────────────────────────
        form = ctk.CTkFrame(self, fg_color=CARD,
                            corner_radius=12, border_width=1,
                            border_color=BORDER)
        form.grid(row=1, column=0, padx=24, pady=8, sticky="ew")
        form.grid_columnconfigure((0, 1, 2), weight=1)

        # URL
        ctk.CTkLabel(form, text="URL de YouTube (video o playlist)",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).grid(row=0, column=0, columnspan=3,
                            padx=18, pady=(16, 2), sticky="w")
        self.url_entry = ctk.CTkEntry(
            form, placeholder_text="https://www.youtube.com/watch?v=…",
            height=40, fg_color=SURFACE, border_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont(size=13))
        self.url_entry.grid(row=1, column=0, columnspan=3,
                            padx=18, pady=(0, 10), sticky="ew")
        self.url_entry.bind("<Return>", lambda _: self._start_download())

        # Calidad
        ctk.CTkLabel(form, text="Calidad", text_color=MUTED,
                     font=ctk.CTkFont(size=12)
                     ).grid(row=2, column=0, padx=18, pady=(0, 2), sticky="w")
        self.quality_var = ctk.StringVar(value="192 kbps — Alta")
        self.quality_menu = ctk.CTkOptionMenu(
            form,
            values=["64 kbps — Bajo", "128 kbps — Normal",
                    "192 kbps — Alta", "256 kbps — Muy alta",
                    "320 kbps — Máxima"],
            variable=self.quality_var,
            fg_color=SURFACE, button_color=ACCENT,
            button_hover_color=ACCENT2, text_color=TEXT,
            font=ctk.CTkFont(size=12))
        self.quality_menu.grid(row=3, column=0, padx=18,
                               pady=(0, 12), sticky="ew")

        # Límite
        ctk.CTkLabel(form, text="Límite de canciones",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).grid(row=2, column=1, padx=8, pady=(0, 2), sticky="w")
        self.limit_entry = ctk.CTkEntry(
            form, placeholder_text="Sin límite",
            height=36, fg_color=SURFACE, border_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont(size=12))
        self.limit_entry.grid(row=3, column=1, padx=8,
                              pady=(0, 12), sticky="ew")

        # Carpeta salida
        ctk.CTkLabel(form, text="Carpeta de salida",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).grid(row=2, column=2, padx=(8, 18), pady=(0, 2), sticky="w")
        self.folder_btn = ctk.CTkButton(
            form, text="📂 descargas",
            fg_color=SURFACE, hover_color=BORDER, text_color=TEXT,
            border_width=1, border_color=BORDER, height=36,
            font=ctk.CTkFont(size=11),
            command=self._pick_folder)
        self.folder_btn.grid(row=3, column=2, padx=(8, 18),
                             pady=(0, 12), sticky="ew")

        # Toggle subcarpeta playlist
        tog_row = ctk.CTkFrame(form, fg_color="transparent")
        tog_row.grid(row=4, column=0, columnspan=3,
                     padx=18, pady=(0, 14), sticky="w")
        self.playlist_folder_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tog_row, text="Crear subcarpeta por playlist",
                      variable=self.playlist_folder_var,
                      progress_color=ACCENT,
                      text_color=MUTED,
                      font=ctk.CTkFont(size=12)).pack(side="left")

        # Botón descargar
        self.dl_btn = ctk.CTkButton(
            form, text="⬇  Descargar MP3",
            height=44, fg_color=ACCENT, hover_color=ACCENT2,
            text_color="white",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_download)
        self.dl_btn.grid(row=5, column=0, columnspan=3,
                         padx=18, pady=(0, 18), sticky="ew")

        # ── Progress card ───────────────────────────────────────────────
        prog_frame = ctk.CTkFrame(self, fg_color=CARD,
                                  corner_radius=12, border_width=1,
                                  border_color=BORDER)
        prog_frame.grid(row=2, column=0, padx=24, pady=4, sticky="ew")
        prog_frame.grid_columnconfigure(0, weight=1)

        prog_top = ctk.CTkFrame(prog_frame, fg_color="transparent")
        prog_top.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="ew")
        prog_top.grid_columnconfigure(0, weight=1)
        self.prog_label = ctk.CTkLabel(
            prog_top, text="En espera…",
            text_color=MUTED, font=ctk.CTkFont(size=12), anchor="w")
        self.prog_label.grid(row=0, column=0, sticky="w")
        self.prog_pct = ctk.CTkLabel(
            prog_top, text="0%",
            text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold"))
        self.prog_pct.grid(row=0, column=1, sticky="e")

        self.prog_bar = ctk.CTkProgressBar(
            prog_frame, progress_color=ACCENT,
            fg_color=BORDER, height=8)
        self.prog_bar.grid(row=1, column=0, padx=18, pady=(0, 8), sticky="ew")
        self.prog_bar.set(0)

        self.log_box = ctk.CTkTextbox(
            prog_frame, height=100, fg_color=SURFACE,
            border_color=BORDER, border_width=1,
            text_color="#aaaacc", font=ctk.CTkFont(family="monospace", size=11),
            wrap="word", state="disabled")
        self.log_box.grid(row=2, column=0, padx=18, pady=(0, 14), sticky="ew")

        # ── Files card ──────────────────────────────────────────────────
        files_outer = ctk.CTkFrame(self, fg_color=CARD,
                                   corner_radius=12, border_width=1,
                                   border_color=BORDER)
        files_outer.grid(row=3, column=0, padx=24, pady=(4, 20), sticky="nsew")
        files_outer.grid_rowconfigure(1, weight=1)
        files_outer.grid_columnconfigure(0, weight=1)

        files_hdr = ctk.CTkFrame(files_outer, fg_color="transparent")
        files_hdr.grid(row=0, column=0, padx=18, pady=(14, 6), sticky="ew")
        files_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(files_hdr, text="📁 Archivos descargados",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(files_hdr, text="🔄", width=34, height=28,
                      fg_color=SURFACE, hover_color=BORDER,
                      text_color=TEXT, border_width=1, border_color=BORDER,
                      command=self._load_files).grid(row=0, column=1)

        self.files_scroll = ctk.CTkScrollableFrame(
            files_outer, fg_color="transparent", corner_radius=0)
        self.files_scroll.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.files_scroll.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.files_scroll, text="Aún no hay archivos descargados",
            text_color=MUTED, font=ctk.CTkFont(size=13))
        self.empty_label.grid(row=0, column=0, pady=24)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Selecciona carpeta de salida",
                                       initialdir=self._output_dir)
        if path:
            self._output_dir = Path(path)
            short = self._output_dir.name or str(self._output_dir)
            self.folder_btn.configure(text=f"📂 {short[:22]}")
            self._load_files()

    def _start_download(self):
        if self._downloading:
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL vacía", "Ingresa una URL de YouTube.")
            return

        quality = self.quality_var.get().split()[0]  # "192"
        limit_raw = self.limit_entry.get().strip()
        limit = int(limit_raw) if limit_raw.isdigit() else None
        playlist_folder = self.playlist_folder_var.get()

        self._downloading = True
        self.dl_btn.configure(state="disabled", text="⏳ Descargando…",
                              fg_color="#555555")
        self._clear_log()
        self.prog_bar.set(0)
        self.prog_label.configure(text="Iniciando…")
        self.prog_pct.configure(text="0%")

        threading.Thread(
            target=run_download,
            args=(url, quality, limit, playlist_folder,
                  self._output_dir,
                  self._cb_log, self._cb_progress,
                  self._cb_track_done, self._cb_finish),
            daemon=True
        ).start()

    def _open_folder(self):
        path = str(self._output_dir)
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    # ------------------------------------------------------------------
    # Callbacks desde el hilo de descarga (thread-safe con after)
    # ------------------------------------------------------------------

    def _cb_log(self, msg: str):
        self.after(0, self._append_log, msg)

    def _cb_progress(self, pct: float, idx: int, total: int, speed_kb: float):
        self.after(0, self._update_progress, pct, idx, total, speed_kb)

    def _cb_track_done(self, artist: str, title: str, size_mb: float, path: str):
        self.after(0, self._add_file_row, artist, title, size_mb, path)

    def _cb_finish(self, ok: int):
        self.after(0, self._on_finish, ok)

    # ------------------------------------------------------------------
    # UI updates (main thread)
    # ------------------------------------------------------------------

    def _append_log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _update_progress(self, pct: float, idx: int, total: int, speed_kb: float):
        self.prog_bar.set(pct / 100)
        self.prog_pct.configure(text=f"{pct:.0f}%")
        self.prog_label.configure(
            text=f"[{idx}/{total}]  {pct:.1f}%  —  {speed_kb:.0f} KB/s")

    def _on_finish(self, ok: int):
        self._downloading = False
        self.dl_btn.configure(state="normal",
                              text="⬇  Descargar MP3",
                              fg_color=ACCENT)
        self.prog_bar.set(1)
        self.prog_pct.configure(text="100%")
        self.prog_label.configure(text="¡Descarga completa!")
        self._load_files()

    # ------------------------------------------------------------------
    # Lista de archivos
    # ------------------------------------------------------------------

    def _load_files(self):
        # Limpiar scroll
        for w in self.files_scroll.winfo_children():
            w.destroy()

        files = sorted(self._output_dir.rglob("*.mp3"))
        if not files:
            ctk.CTkLabel(self.files_scroll, text="Aún no hay archivos descargados",
                         text_color=MUTED, font=ctk.CTkFont(size=13)
                         ).grid(row=0, column=0, pady=24)
            return

        for i, mp3 in enumerate(files):
            parts = mp3.stem.split(" - ", 1)
            artist = parts[0] if len(parts) > 1 else ""
            title  = parts[1] if len(parts) > 1 else mp3.stem
            size_mb = round(mp3.stat().st_size / 1_048_576, 1)
            self._add_file_row(artist, title, size_mb, str(mp3), row=i)

    def _add_file_row(self, artist: str, title: str, size_mb: float,
                      path: str, row: int = None):
        # Si ya existe la fila (al recargar) no duplicar
        if row is None:
            row = len(self.files_scroll.winfo_children())

        row_frame = ctk.CTkFrame(self.files_scroll, fg_color=SURFACE,
                                 corner_radius=8, border_width=1,
                                 border_color=BORDER)
        row_frame.grid(row=row, column=0, pady=3, sticky="ew")
        row_frame.grid_columnconfigure(1, weight=1)

        # Ícono
        ctk.CTkLabel(row_frame, text="🎵", font=ctk.CTkFont(size=20),
                     width=40).grid(row=0, rowspan=2, column=0,
                                    padx=(10, 0), pady=8)
        # Título
        ctk.CTkLabel(row_frame, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT, anchor="w"
                     ).grid(row=0, column=1, padx=10, pady=(8, 0), sticky="ew")
        # Artista + tamaño
        meta = f"{artist}  ·  {size_mb} MB" if artist else f"{size_mb} MB"
        ctk.CTkLabel(row_frame, text=meta,
                     font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w"
                     ).grid(row=1, column=1, padx=10, pady=(0, 8), sticky="ew")

        # Botones
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_frame.grid(row=0, rowspan=2, column=2, padx=8)

        ctk.CTkButton(
            btn_frame, text="📂", width=32, height=28,
            fg_color=SURFACE, hover_color=BORDER, text_color=TEXT,
            border_width=1, border_color=BORDER,
            command=lambda p=path: self._reveal_file(p)
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="▶ Reproducir", width=100, height=28,
            fg_color=ACCENT, hover_color=ACCENT2, text_color="white",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda p=path: self._play_file(p)
        ).pack(side="left", padx=2)

    def _reveal_file(self, path: str):
        """Abre el explorador de archivos en la carpeta del MP3."""
        folder = str(Path(path).parent)
        if sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        elif sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def _play_file(self, path: str):
        """Abre el MP3 con el reproductor predeterminado del sistema."""
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()

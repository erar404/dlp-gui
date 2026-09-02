import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import queue
import os
import shlex
import sys
import json
import shutil
import urllib.request
import zipfile
import tempfile
from pathlib import Path

# ── Config persistence ─────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent

CONFIG_FILE = _BASE / "dlp-ui-config.json"

VERSION = "1.0.0"
GITHUB_REPO     = "erar404/dlp-gui"
APP_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

YTDLP_RELEASE_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
)

FFMPEG_RELEASE_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)

COMMON_YTDLP_PATHS = [
    r"C:\ERAR\yt-dlp\dist\yt-dlp.exe",
    r"C:\Program Files\yt-dlp\yt-dlp.exe",
    r"C:\Program Files (x86)\yt-dlp\yt-dlp.exe",
    str(Path.home() / "yt-dlp" / "yt-dlp.exe"),
    str(Path.home() / "AppData" / "Local" / "Programs" / "yt-dlp" / "yt-dlp.exe"),
    str(Path.home() / "AppData" / "Local" / "yt-dlp" / "yt-dlp.exe"),
    str(_BASE / "yt-dlp" / "yt-dlp.exe"),
    str(_BASE / "yt-dlp.exe"),
]

COMMON_FFMPEG_PATHS = [
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    str(Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe"),
    str(Path.home() / "AppData" / "Local" / "Programs" / "ffmpeg" / "bin" / "ffmpeg.exe"),
    str(_BASE / "ffmpeg" / "ffmpeg.exe"),
    str(_BASE / "ffmpeg.exe"),
]


def _load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _parse_ver(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)


def find_ytdlp() -> str:
    """Return the first valid yt-dlp executable path, or empty string."""
    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "yt-dlp.exe"
        if p.exists():
            return str(p)
    for p in COMMON_YTDLP_PATHS:
        if os.path.isfile(p):
            return p
    return ""


def find_ffmpeg() -> str:
    """Return the first valid ffmpeg executable path, or empty string."""
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "ffmpeg" / "ffmpeg.exe"
        if p.exists():
            return str(p)
    for p in COMMON_FFMPEG_PATHS:
        if os.path.isfile(p):
            return p
    return ""


def _extract_bundled():
    """Copy deps bundled inside the PyInstaller EXE next to it on first launch."""
    if not getattr(sys, "frozen", False):
        return
    bundle = Path(sys._MEIPASS)
    pairs = [
        (bundle / "yt-dlp.exe",            _BASE / "yt-dlp"  / "yt-dlp.exe"),
        (bundle / "ffmpeg" / "ffmpeg.exe",  _BASE / "ffmpeg"  / "ffmpeg.exe"),
        (bundle / "ffmpeg" / "ffprobe.exe", _BASE / "ffmpeg"  / "ffprobe.exe"),
    ]
    for src, dst in pairs:
        try:
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
        except Exception:
            pass  # Non-fatal — sys._MEIPASS fallback still works

_extract_bundled()
_cfg = _load_config()
YT_DLP = _cfg.get("ytdlp_path") or find_ytdlp()
FFMPEG  = _cfg.get("ffmpeg_path") or find_ffmpeg()

# ── Colour palette ─────────────────────────────────────────────────────────────
BG0  = "#121212"
BG1  = "#1c1c1c"
BG2  = "#282828"
BG3  = "#373737"
FG0  = "#ffffff"
FG1  = "#aaaaaa"
FG2  = "#6e6e6e"
RED  = "#dc2626"
BLUE = "#64a0ff"

LOG_GREEN = "#64dc64"
LOG_RED   = "#ff6464"
LOG_GRAY  = "#d2d2d2"
LOG_OK    = "#50dc50"
LOG_FAIL  = "#ff5050"
LOG_WARN  = "#f59e0b"

# ── Format definitions ─────────────────────────────────────────────────────────
VIDEO_QUALITIES = {
    "Best available": "",
    "4K (2160p)": "[height<=2160]",
    "1440p": "[height<=1440]",
    "1080p": "[height<=1080]",
    "720p": "[height<=720]",
    "480p": "[height<=480]",
    "360p": "[height<=360]",
}

AUDIO_QUALITIES = {
    "Best (VBR)": "0",
    "320 Kbps": "320K",
    "256 Kbps": "256K",
    "192 Kbps": "192K",
    "128 Kbps": "128K",
}

FORMAT_TYPES = {
    "Best Quality (auto)": "video",
    "MP4": "video",
    "MKV": "video",
    "WebM": "video",
    "MP3": "audio",
    "M4A": "audio",
    "AAC": "audio",
    "FLAC": "audio",
    "WAV": "audio",
    "OPUS": "audio",
    "OGG": "audio",
}


def build_args(fmt_key, qual_key, dest, url, settings):
    fmt_type = FORMAT_TYPES[fmt_key]
    args = []

    if fmt_type == "audio":
        brate = AUDIO_QUALITIES[qual_key]
        afmt = {
            "MP3": "mp3", "M4A": "m4a", "AAC": "aac",
            "FLAC": "flac", "WAV": "wav", "OPUS": "opus", "OGG": "vorbis",
        }.get(fmt_key, "mp3")
        args += ["-f", "bestaudio", "-x", "--audio-format", afmt, "--audio-quality", brate]
    else:
        q = VIDEO_QUALITIES[qual_key]
        if fmt_key == "Best Quality (auto)":
            args += ["-f", "bestvideo+bestaudio/best"]
        elif fmt_key == "MP4":
            if q:
                args += ["-f", f"bestvideo{q}[ext=mp4]+bestaudio[ext=m4a]/bestvideo{q}+bestaudio/best{q}"]
            else:
                args += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"]
            args += ["--merge-output-format", "mp4"]
        elif fmt_key == "MKV":
            if q:
                args += ["-f", f"bestvideo{q}+bestaudio/best{q}"]
            else:
                args += ["-f", "bestvideo+bestaudio/best"]
            args += ["--merge-output-format", "mkv"]
        elif fmt_key == "WebM":
            if q:
                args += ["-f", f"bestvideo{q}[ext=webm]+bestaudio[ext=webm]/best{q}"]
            else:
                args += ["-f", "bestvideo[ext=webm]+bestaudio[ext=webm]/best"]
        else:
            args += ["-f", "bestvideo+bestaudio/best"]

    if settings["embed_thumbnail"]: args.append("--embed-thumbnail")
    if settings["embed_metadata"]:  args.append("--embed-metadata")
    if settings["embed_chapters"]:  args.append("--embed-chapters")
    if settings["sponsorblock"]:    args += ["--sponsorblock-remove", "all"]

    remux = settings["remux_to"]
    if remux and remux != "None":
        args += ["--remux-video", remux.lower()]

    if settings["write_subs"]:
        args.append("--write-subs")
        if settings["sub_langs"]:
            args += ["--sub-langs", settings["sub_langs"]]
    if settings["write_auto_subs"]:
        args.append("--write-auto-subs")

    if settings["rate_limit"]:
        args += ["--limit-rate", settings["rate_limit"]]
    if settings["concurrent_frags"] > 1:
        args += ["-N", str(settings["concurrent_frags"])]

    cookies = settings["cookies"]
    if cookies and cookies != "None":
        args += ["--cookies-from-browser", cookies.lower()]

    if settings["playlist_mode"] == "single":
        args.append("--no-playlist")
    elif settings["playlist_mode"] == "full":
        args.append("--yes-playlist")

    args += ["-o", os.path.join(dest, settings["out_template"]), url]
    return args


class PlaceholderEntry(tk.Entry):
    def __init__(self, parent, placeholder="", **kw):
        self._ph = placeholder
        self._real_fg = kw.pop("fg", FG0)
        super().__init__(parent, fg=FG2 if placeholder else self._real_fg, **kw)
        if placeholder:
            self.insert(0, placeholder)
            self.bind("<FocusIn>",  self._in)
            self.bind("<FocusOut>", self._out)

    def _in(self, _):
        if self.get() == self._ph:
            self.delete(0, "end")
            self.config(fg=self._real_fg)

    def _out(self, _):
        if not self.get():
            self.insert(0, self._ph)
            self.config(fg=FG2)

    def value(self):
        v = self.get()
        return "" if v == self._ph else v


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YT-DLP Downloader")
        self.geometry("680x820")
        self.minsize(580, 480)
        self.configure(bg=BG0)
        self.proc = None
        self._q = queue.Queue()
        self.ytdlp_path = YT_DLP
        self.ffmpeg_path = FFMPEG
        self._build()
        self._poll()

    # ── UI construction ────────────────────────────────────────────────────────
    def _build(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook",     background=BG0, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG1, foreground=FG1,
                        padding=[12, 4], font=("Segoe UI", 9))
        style.map("TNotebook.Tab",
                  background=[("selected", BG2)],
                  foreground=[("selected", FG0)])
        style.configure("TCombobox",
                        fieldbackground=BG2, background=BG2, foreground=FG0,
                        selectbackground=BG3, selectforeground=FG0,
                        arrowcolor=FG1, bordercolor=BG3, insertcolor=FG0)
        style.map("TCombobox",
                  fieldbackground=[("readonly", BG2)],
                  background=[("readonly", BG2)],
                  foreground=[("readonly", FG0)])

        self._nb = nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_dl  = tk.Frame(nb, bg=BG0)
        self.tab_cfg = tk.Frame(nb, bg=BG0)
        nb.add(self.tab_dl,  text="  Download  ")
        nb.add(self.tab_cfg, text="  Settings  ")

        self._build_download()
        self._build_settings()

        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ── Scrolling ──────────────────────────────────────────────────────────────
    def _on_tab_changed(self, _=None):
        if self._nb.index(self._nb.select()) == 1:
            self.bind_all("<MouseWheel>", self._scroll_cfg)
        else:
            self.unbind_all("<MouseWheel>")

    def _scroll_cfg(self, e):
        self._cfg_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    # ── Download tab ───────────────────────────────────────────────────────────
    def _build_download(self):
        p = self.tab_dl
        p.columnconfigure(0, weight=1)
        p.rowconfigure(7, weight=1)   # log row expands

        # URL
        tk.Label(p, text="YouTube / Video URL", bg=BG0, fg=FG1,
                 font=("Segoe UI", 10)).grid(row=0, column=0, padx=16, pady=(14, 3), sticky="W")
        self.txt_url = PlaceholderEntry(
            p, placeholder="Paste a link here...",
            bg=BG2, fg=FG0, insertbackground=FG0,
            relief="solid", bd=1, font=("Segoe UI", 9))
        self.txt_url.grid(row=1, column=0, padx=16, sticky="EW", ipady=5)

        # Format / Quality
        fq = tk.Frame(p, bg=BG0)
        fq.grid(row=2, column=0, padx=16, pady=(10, 0), sticky="EW")
        fq.columnconfigure(0, weight=1)
        fq.columnconfigure(1, weight=1)
        tk.Label(fq, text="Format", bg=BG0, fg=FG1,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="W")
        tk.Label(fq, text="Quality / Resolution", bg=BG0, fg=FG1,
                 font=("Segoe UI", 10)).grid(row=0, column=1, padx=(10, 0), sticky="W")
        self.cbo_fmt = ttk.Combobox(fq, values=list(FORMAT_TYPES),
                                     state="readonly", font=("Segoe UI", 9))
        self.cbo_fmt.grid(row=1, column=0, sticky="EW", ipady=2, pady=(3, 0))
        self.cbo_fmt.current(0)
        self.cbo_qual = ttk.Combobox(fq, values=list(VIDEO_QUALITIES),
                                      state="readonly", font=("Segoe UI", 9))
        self.cbo_qual.grid(row=1, column=1, sticky="EW", padx=(10, 0), ipady=2, pady=(3, 0))
        self.cbo_qual.current(0)
        self.cbo_fmt.bind("<<ComboboxSelected>>", self._fmt_changed)

        # Destination
        tk.Label(p, text="Destination Folder", bg=BG0, fg=FG1,
                 font=("Segoe UI", 10)).grid(row=3, column=0, padx=16, pady=(10, 3), sticky="W")
        dest = tk.Frame(p, bg=BG0)
        dest.grid(row=4, column=0, padx=16, sticky="EW")
        dest.columnconfigure(0, weight=1)
        self.txt_dest = tk.Entry(dest, bg=BG2, fg=FG0, insertbackground=FG0,
                                  relief="solid", bd=1, font=("Segoe UI", 9))
        self.txt_dest.insert(0, str(Path.home() / "Videos"))
        self.txt_dest.grid(row=0, column=0, sticky="EW", ipady=5)
        tk.Button(dest, text="Browse...", bg=BG2, fg=FG0, relief="flat", bd=0,
                  cursor="hand2", font=("Segoe UI", 9), command=self._browse,
                  highlightthickness=1, highlightbackground=BG3,
                  activebackground=BG3, activeforeground=FG0).grid(
                      row=0, column=1, padx=(6, 0), ipady=5)

        # Download button
        self.btn_dl = tk.Button(
            p, text="Download", bg=RED, fg=FG0, relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI Semibold", 11), command=self._start,
            highlightthickness=1, highlightbackground=RED,
            activebackground="#b91c1c", activeforeground=FG0)
        self.btn_dl.grid(row=5, column=0, padx=16, pady=(10, 0), sticky="EW", ipady=10)

        # Log
        tk.Label(p, text="Output Log", bg=BG0, fg=FG1,
                 font=("Segoe UI", 10)).grid(row=6, column=0, padx=16, pady=(12, 3), sticky="W")
        log_f = tk.Frame(p, bg=BG0)
        log_f.grid(row=7, column=0, padx=16, sticky="NSEW")
        log_f.columnconfigure(0, weight=1)
        log_f.rowconfigure(0, weight=1)

        self.log = tk.Text(log_f, bg="#0a0a0a", fg=LOG_GRAY, state="disabled",
                           relief="flat", bd=0, wrap="word", font=self._mono())
        self.log.grid(row=0, column=0, sticky="NSEW")

        sb = tk.Scrollbar(log_f, command=self.log.yview, bg=BG2, troughcolor=BG1,
                          activebackground=BG3)
        sb.grid(row=0, column=1, sticky="NS")
        self.log.config(yscrollcommand=sb.set)

        for tag, color in [("err",  LOG_RED),  ("dl",   LOG_GREEN),
                            ("info", BLUE),      ("gray", LOG_GRAY),
                            ("blue", BLUE),      ("ok",   LOG_OK),
                            ("fail", LOG_FAIL)]:
            self.log.tag_configure(tag, foreground=color)

        # Clear log
        tk.Button(p, text="Clear log", bg=BG1, fg=FG2, relief="flat", bd=0,
                  cursor="hand2", font=("Segoe UI", 8), command=self._clear,
                  highlightthickness=1, highlightbackground=BG2,
                  activebackground=BG3, activeforeground=FG0).grid(
                      row=8, column=0, padx=16, pady=(4, 10), sticky="EW")

    def _mono(self):
        try:
            import tkinter.font as tkf
            return ("Cascadia Code", 8) if "Cascadia Code" in tkf.families() else ("Consolas", 9)
        except Exception:
            return ("Consolas", 9)

    # ── Settings tab ──────────────────────────────────────────────────────────
    def _build_settings(self):
        p = self.tab_cfg
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)

        # ── Scrollable canvas ──────────────────────────────────────────────────
        self._cfg_canvas = canvas = tk.Canvas(p, bg=BG0, highlightthickness=0)
        vsb = tk.Scrollbar(p, orient="vertical", command=canvas.yview,
                           bg=BG2, troughcolor=BG1, activebackground=BG3)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="NS")
        canvas.grid(row=0, column=0, sticky="NSEW")

        inner = tk.Frame(canvas, bg=BG0)
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        inner.columnconfigure(0, weight=1)

        # ── Local widget factories ─────────────────────────────────────────────
        def grp(title):
            f = tk.LabelFrame(inner, text=title, bg=BG0, fg=FG1,
                              bd=1, relief="groove", font=("Segoe UI", 9))
            f.pack(fill="x", padx=10, pady=(6, 0))
            f.columnconfigure(1, weight=1)
            return f

        def sbtn(parent, text, cmd, fg=FG0, border=BG3):
            return tk.Button(parent, text=text, bg=BG2, fg=fg, relief="flat", bd=0,
                             cursor="hand2", font=("Segoe UI", 9), command=cmd,
                             highlightthickness=1, highlightbackground=border,
                             activebackground=BG3, activeforeground=FG0)

        def ent(parent, default=""):
            e = tk.Entry(parent, bg=BG2, fg=FG0, insertbackground=FG0,
                         relief="solid", bd=1, font=("Segoe UI", 9))
            if default:
                e.insert(0, default)
            return e

        def cbo(parent, vals):
            c = ttk.Combobox(parent, values=vals, state="readonly", font=("Segoe UI", 9))
            c.current(0)
            return c

        def chk(parent, text):
            var = tk.BooleanVar()
            cb = tk.Checkbutton(parent, text=text, variable=var, bg=BG0, fg=FG1,
                                selectcolor=BG2, activebackground=BG0,
                                activeforeground=FG0, font=("Segoe UI", 10))
            return cb, var

        def spn(parent, lo, hi, default):
            s = tk.Spinbox(parent, from_=lo, to=hi, bg=BG2, fg=FG0,
                           insertbackground=FG0, buttonbackground=BG3,
                           relief="solid", bd=1, font=("Segoe UI", 9), width=5)
            s.delete(0, "end"); s.insert(0, str(default))
            return s

        def slbl(parent):
            lbl = tk.Label(parent, text="", bg=BG0, fg=FG2,
                           font=("Segoe UI", 9), anchor="w")
            lbl.bind("<Configure>",
                     lambda e, l=lbl: l.configure(wraplength=max(1, e.width - 4)))
            return lbl

        def lbl10(parent, text):
            return tk.Label(parent, text=text, bg=BG0, fg=FG1, font=("Segoe UI", 10))

        # ── Dependencies ──────────────────────────────────────────────────────
        g = grp("Dependencies")
        g.columnconfigure(1, weight=1)

        tk.Label(g, text="yt-dlp:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9, "bold")).grid(
                     row=0, column=0, padx=(8, 4), pady=(10, 3), sticky="W")
        self.txt_ytdlp = ent(g, self.ytdlp_path)
        self.txt_ytdlp.grid(row=0, column=1, padx=4, pady=(10, 3), sticky="EW", ipady=3)
        sbtn(g, "Browse",      self._browse_ytdlp    ).grid(row=0, column=2, padx=4,    pady=(10, 3), ipady=3)
        sbtn(g, "Auto-detect", self._autodetect_ytdlp).grid(row=0, column=3, padx=4,    pady=(10, 3), ipady=3)
        self.btn_get_ytdlp = sbtn(g, "↓ Get yt-dlp", self._download_ytdlp)
        self.btn_get_ytdlp.grid(row=0, column=4, padx=(4, 8), pady=(10, 3), ipady=3)

        self.lbl_ytdlp_status = slbl(g)
        self.lbl_ytdlp_status.grid(row=1, column=0, columnspan=5,
                                    padx=8, pady=(0, 4), sticky="EW")

        tk.Label(g, text="ffmpeg:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9, "bold")).grid(
                     row=2, column=0, padx=(8, 4), pady=(4, 3), sticky="W")
        self.txt_ffmpeg = ent(g, self.ffmpeg_path)
        self.txt_ffmpeg.grid(row=2, column=1, padx=4, pady=(4, 3), sticky="EW", ipady=3)
        sbtn(g, "Browse",      self._browse_ffmpeg    ).grid(row=2, column=2, padx=4,    pady=(4, 3), ipady=3)
        sbtn(g, "Auto-detect", self._autodetect_ffmpeg).grid(row=2, column=3, padx=4,    pady=(4, 3), ipady=3)
        self.btn_get_ffmpeg = sbtn(g, "↓ Get ffmpeg", self._download_ffmpeg)
        self.btn_get_ffmpeg.grid(row=2, column=4, padx=(4, 8), pady=(4, 3), ipady=3)

        self.lbl_ffmpeg_status = slbl(g)
        self.lbl_ffmpeg_status.grid(row=3, column=0, columnspan=5,
                                     padx=8, pady=(0, 4), sticky="EW")

        self.btn_quick_setup = tk.Button(
            g, text="⚡  Quick Setup  —  download yt-dlp + ffmpeg",
            bg=BG2, fg=BLUE, relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9), command=self._quick_setup,
            highlightthickness=1, highlightbackground=BLUE,
            activebackground=BG3, activeforeground=FG0)
        self.btn_quick_setup.grid(row=4, column=0, columnspan=5,
                                   padx=8, pady=(2, 8), sticky="EW", ipady=3)

        self.txt_ytdlp.bind("<FocusOut>", self._on_ytdlp_entry_change)
        self.txt_ytdlp.bind("<Return>",   self._on_ytdlp_entry_change)
        self.txt_ffmpeg.bind("<FocusOut>", self._on_ffmpeg_entry_change)
        self.txt_ffmpeg.bind("<Return>",   self._on_ffmpeg_entry_change)
        self._refresh_ytdlp_status()
        self._refresh_ffmpeg_status()

        # ── Post-Processing ───────────────────────────────────────────────────
        g = grp("Post-Processing")
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)

        cb, self.v_thumb    = chk(g, "Embed thumbnail as cover art")
        cb.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="W")
        cb, self.v_meta     = chk(g, "Embed metadata (title, artist...)")
        cb.grid(row=1, column=0, padx=8, pady=2, sticky="W")
        cb, self.v_chapters = chk(g, "Embed chapter markers")
        cb.grid(row=2, column=0, padx=8, pady=(2, 8), sticky="W")

        cb, self.v_sponsor  = chk(g, "SponsorBlock: remove sponsored segments")
        cb.grid(row=0, column=1, padx=8, pady=(8, 2), sticky="W")

        rr = tk.Frame(g, bg=BG0)
        rr.grid(row=1, column=1, rowspan=2, padx=8, pady=(2, 8), sticky="EW")
        rr.columnconfigure(1, weight=1)
        lbl10(rr, "Remux to:").grid(   row=0, column=0, padx=(0, 6), pady=3, sticky="W")
        self.cbo_remux = cbo(rr, ["None","mp4","mkv","mov","webm","avi","flv"])
        self.cbo_remux.grid(row=0, column=1, sticky="EW", ipady=2)
        lbl10(rr, "Re-encode to:").grid(row=1, column=0, padx=(0, 6), pady=3, sticky="W")
        self.cbo_recode = cbo(rr, ["None","mp4","mkv","mov","webm","mp3","m4a","wav"])
        self.cbo_recode.grid(row=1, column=1, sticky="EW", ipady=2)

        # ── Subtitles ─────────────────────────────────────────────────────────
        g = grp("Subtitles")
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)

        cb, self.v_subs      = chk(g, "Download subtitles")
        cb.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="W")
        cb, self.v_auto_subs = chk(g, "Include auto-generated subtitles")
        cb.grid(row=1, column=0, padx=8, pady=(2, 8), sticky="W")

        sr = tk.Frame(g, bg=BG0)
        sr.grid(row=0, column=1, rowspan=2, padx=8, pady=8, sticky="EW")
        sr.columnconfigure(0, weight=1)
        lbl10(sr, "Languages (comma-separated, e.g. en,ja):").grid(
            row=0, column=0, sticky="W", pady=(0, 3))
        self.txt_sub_langs = ent(sr, "en")
        self.txt_sub_langs.grid(row=1, column=0, sticky="EW", ipady=3)

        # ── Network ───────────────────────────────────────────────────────────
        g = grp("Network")
        g.columnconfigure(0, weight=1)
        g.columnconfigure(0, weight=1)

        top = tk.Frame(g, bg=BG0)
        top.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="EW")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(2, weight=1)

        lbl10(top, "Rate limit (e.g. 5M, 500K):").grid(row=0, column=0, sticky="W")
        self.txt_rate = ent(top)
        self.txt_rate.grid(row=1, column=0, sticky="EW", ipady=3)

        lbl10(top, "Concurrent frags:").grid(row=0, column=1, padx=(12, 4), sticky="W")
        self.spn_frags = spn(top, 1, 32, 1)
        self.spn_frags.grid(row=1, column=1, padx=(12, 4), ipady=3)

        lbl10(top, "Cookies from browser:").grid(row=0, column=2, sticky="W")
        self.cbo_cookies = cbo(top, ["None","chrome","firefox","edge","brave",
                                      "opera","safari","vivaldi","chromium"])
        self.cbo_cookies.grid(row=1, column=2, sticky="EW", ipady=2)

        lbl10(top, "Retries:").grid(row=0, column=3, padx=(12, 0), sticky="W")
        self.spn_retries = spn(top, 1, 50, 10)
        self.spn_retries.grid(row=1, column=3, padx=(12, 0), ipady=3)

        bot = tk.Frame(g, bg=BG0)
        bot.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="EW")
        bot.columnconfigure(0, weight=1)
        lbl10(bot, "Proxy (e.g. socks5://127.0.0.1:1080):").grid(
            row=0, column=0, sticky="W", pady=(0, 3))
        self.txt_proxy = ent(bot)
        self.txt_proxy.grid(row=1, column=0, sticky="EW", ipady=3)

        # ── Playlist ──────────────────────────────────────────────────────────
        g = grp("Playlist Handling")
        g.columnconfigure(0, weight=1)

        self.v_playlist = tk.StringVar(value="auto")
        pl = tk.Frame(g, bg=BG0)
        pl.grid(row=0, column=0, padx=8, pady=8, sticky="W")
        for text, val in [("Auto (let yt-dlp decide)", "auto"),
                           ("Single video only",        "single"),
                           ("Always full playlist",     "full")]:
            tk.Radiobutton(pl, text=text, variable=self.v_playlist, value=val,
                           bg=BG0, fg=FG1, selectcolor=BG2,
                           activebackground=BG0, activeforeground=FG0,
                           font=("Segoe UI", 10)).pack(side="left", padx=(0, 16))

        # ── Output template ───────────────────────────────────────────────────
        g = grp("Output Filename Template")
        g.columnconfigure(0, weight=1)

        lbl10(g, "Template (%(title)s.%(ext)s = default):").grid(
            row=0, column=0, padx=8, pady=(8, 3), sticky="W")
        self.txt_tmpl = ent(g, "%(title)s.%(ext)s")
        self.txt_tmpl.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="EW", ipady=3)

        # ── Extra args ────────────────────────────────────────────────────────
        g = grp("Extra yt-dlp Arguments")
        g.columnconfigure(0, weight=1)

        lbl10(g, "Any additional flags appended verbatim:").grid(
            row=0, column=0, padx=8, pady=(8, 3), sticky="W")
        self.txt_extra = ent(g)
        self.txt_extra.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="EW", ipady=3)

        # ── App Update ────────────────────────────────────────────────────────
        g = grp("App Update")
        g.columnconfigure(0, weight=1)

        top_row = tk.Frame(g, bg=BG0)
        top_row.grid(row=0, column=0, padx=8, pady=(8, 3), sticky="EW")
        top_row.columnconfigure(0, weight=1)

        tk.Label(top_row, text=f"Current version: v{VERSION}",
                 bg=BG0, fg=FG1, font=("Segoe UI", 10)).grid(
                     row=0, column=0, sticky="W")
        self.btn_check_update = sbtn(top_row, "Check for Updates",
                                      self._check_app_update)
        self.btn_check_update.grid(row=0, column=1, padx=(8, 0), ipady=3)

        self.lbl_update_status = slbl(g)
        self.lbl_update_status.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="EW")

        tk.Frame(inner, bg=BG0, height=8).pack()

    # ── yt-dlp path helpers ────────────────────────────────────────────────────
    def _refresh_ytdlp_status(self):
        path = self.ytdlp_path
        if path and os.path.isfile(path):
            self.lbl_ytdlp_status.config(text="Checking version...", fg=FG1)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↑ Update yt-dlp")
            self._check_ytdlp_version()
        elif path:
            self.lbl_ytdlp_status.config(text="✗ Not found — verify the path above", fg=LOG_RED)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↓ Get yt-dlp")
        else:
            self.lbl_ytdlp_status.config(text="No path set — use Browse or ↓ Get yt-dlp", fg=FG2)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↓ Get yt-dlp")

    def _check_ytdlp_version(self):
        path = self.ytdlp_path

        def _status(text, color):
            self.after(0, lambda t=text, c=color: self.lbl_ytdlp_status.config(text=t, fg=c))

        def run():
            # ── 1. Incomplete file ────────────────────────────────────────────
            try:
                size = os.path.getsize(path)
            except OSError:
                _status("⚠ Cannot read file — may be incomplete. Click ↑ Update yt-dlp", LOG_RED)
                return
            if size < 1_000_000:
                kb = size // 1024
                _status(
                    f"⚠ File too small ({kb} KB) — incomplete download. Click ↑ Update yt-dlp",
                    LOG_RED,
                )
                return

            # ── 2. Runs cleanly ───────────────────────────────────────────────
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                r = subprocess.run(
                    [path, "--version"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=flags,
                )
                local_ver = r.stdout.strip()
                if r.returncode != 0 or not local_ver:
                    _status(
                        "⚠ yt-dlp failed to start — binary may be corrupted. Click ↑ Update yt-dlp",
                        LOG_RED,
                    )
                    return
            except Exception as exc:
                _status(f"⚠ Could not run yt-dlp: {exc}", LOG_RED)
                return

            # ── 3. Compare with GitHub latest release ─────────────────────────
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                    headers={"User-Agent": "dlp-ui/1.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    latest_ver = json.loads(resp.read()).get("tag_name", "").lstrip("v")
            except Exception:
                _status(f"✓ v{local_ver} — could not check for updates (offline?)", LOG_OK)
                return

            if _parse_ver(local_ver) >= _parse_ver(latest_ver):
                _status(f"✓ v{local_ver} — up to date", LOG_OK)
            else:
                _status(
                    f"⚠ Outdated: v{local_ver} → v{latest_ver} available — click ↑ Update yt-dlp",
                    LOG_WARN,
                )

        threading.Thread(target=run, daemon=True).start()

    def _set_ytdlp_path(self, path: str):
        self.ytdlp_path = path
        self.txt_ytdlp.delete(0, "end")
        self.txt_ytdlp.insert(0, path)
        cfg = _load_config()
        cfg["ytdlp_path"] = path
        _save_config(cfg)
        self._refresh_ytdlp_status()

    def _on_ytdlp_entry_change(self, _=None):
        self._set_ytdlp_path(self.txt_ytdlp.get().strip())

    def _browse_ytdlp(self):
        path = filedialog.askopenfilename(
            title="Locate yt-dlp executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=str(Path(self.ytdlp_path).parent) if self.ytdlp_path else str(Path.home()),
        )
        if path:
            self._set_ytdlp_path(path)

    def _autodetect_ytdlp(self):
        found = find_ytdlp()
        if found:
            self._set_ytdlp_path(found)
        else:
            self.lbl_ytdlp_status.config(
                text="Auto-detect failed — use Browse or ↓ Get yt-dlp to download it", fg=LOG_RED)

    def _download_ytdlp(self):
        dest_dir = _BASE / "yt-dlp"
        dest_file = dest_dir / "yt-dlp.exe"
        action = "Updating" if self.ytdlp_path and os.path.isfile(self.ytdlp_path) else "Downloading"
        self.btn_get_ytdlp.config(state="disabled", text=f"{action}...")

        def reporthook(count, block_size, total_size):
            mb_done = count * block_size / 1_048_576
            if total_size > 0:
                pct = min(100, count * block_size * 100 // total_size)
                total_mb = total_size / 1_048_576
                msg = f"Downloading yt-dlp... {mb_done:.1f} / {total_mb:.1f} MB ({pct}%)"
            else:
                msg = f"Downloading yt-dlp... {mb_done:.1f} MB"
            self.after(0, lambda m=msg: self.lbl_ytdlp_status.config(text=m, fg=BLUE))

        def run():
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(YTDLP_RELEASE_URL, str(dest_file), reporthook)
                self.after(0, lambda: self._set_ytdlp_path(str(dest_file)))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self.lbl_ytdlp_status.config(
                    text=f"Download failed: {e}", fg=LOG_RED))
            finally:
                self.after(0, lambda: self.btn_get_ytdlp.config(
                    state="normal", text="↓ Get yt-dlp"))

        threading.Thread(target=run, daemon=True).start()

    # ── ffmpeg path helpers ────────────────────────────────────────────────────
    def _refresh_ffmpeg_status(self):
        path = self.ffmpeg_path
        if path and os.path.isfile(path):
            self.lbl_ffmpeg_status.config(text="Checking version...", fg=FG1)
            if hasattr(self, "btn_get_ffmpeg"):
                self.btn_get_ffmpeg.config(text="↑ Update ffmpeg")
            self._check_ffmpeg_version()
        elif path:
            self.lbl_ffmpeg_status.config(text="✗ Not found — verify the path above", fg=LOG_RED)
            if hasattr(self, "btn_get_ffmpeg"):
                self.btn_get_ffmpeg.config(text="↓ Get ffmpeg")
        else:
            self.lbl_ffmpeg_status.config(
                text="Not set — use Browse or ↓ Get ffmpeg (required for merging formats)",
                fg=FG2)
            if hasattr(self, "btn_get_ffmpeg"):
                self.btn_get_ffmpeg.config(text="↓ Get ffmpeg")

    def _check_ffmpeg_version(self):
        path = self.ffmpeg_path

        def _status(text, color):
            self.after(0, lambda t=text, c=color: self.lbl_ffmpeg_status.config(text=t, fg=c))

        def run():
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                r = subprocess.run(
                    [path, "-version"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=flags,
                )
                if r.returncode != 0:
                    _status("⚠ ffmpeg failed to start — binary may be corrupted. Click ↑ Update ffmpeg", LOG_RED)
                    return
                first_line = r.stdout.splitlines()[0] if r.stdout else ""
                ver = first_line.split("version")[-1].strip().split()[0] if "version" in first_line else "?"
                _status(f"✓ ffmpeg {ver}", LOG_OK)
            except Exception as exc:
                _status(f"⚠ Could not run ffmpeg: {exc}", LOG_RED)

        threading.Thread(target=run, daemon=True).start()

    def _set_ffmpeg_path(self, path: str):
        self.ffmpeg_path = path
        self.txt_ffmpeg.delete(0, "end")
        self.txt_ffmpeg.insert(0, path)
        cfg = _load_config()
        cfg["ffmpeg_path"] = path
        _save_config(cfg)
        self._refresh_ffmpeg_status()

    def _on_ffmpeg_entry_change(self, _=None):
        self._set_ffmpeg_path(self.txt_ffmpeg.get().strip())

    def _browse_ffmpeg(self):
        path = filedialog.askopenfilename(
            title="Locate ffmpeg executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=str(Path(self.ffmpeg_path).parent) if self.ffmpeg_path else str(Path.home()),
        )
        if path:
            self._set_ffmpeg_path(path)

    def _autodetect_ffmpeg(self):
        found = find_ffmpeg()
        if found:
            self._set_ffmpeg_path(found)
        else:
            self.lbl_ffmpeg_status.config(
                text="Auto-detect failed — use Browse or ↓ Get ffmpeg to download it", fg=LOG_RED)

    def _download_ffmpeg(self):
        dest_dir = _BASE / "ffmpeg"
        action = "Updating" if self.ffmpeg_path and os.path.isfile(self.ffmpeg_path) else "Downloading"
        self.btn_get_ffmpeg.config(state="disabled", text=f"{action}...")

        def _status(text, color):
            self.after(0, lambda t=text, c=color: self.lbl_ffmpeg_status.config(text=t, fg=c))

        def reporthook(count, block_size, total_size):
            mb_done = count * block_size / 1_048_576
            if total_size > 0:
                pct = min(100, count * block_size * 100 // total_size)
                total_mb = total_size / 1_048_576
                msg = f"Downloading ffmpeg... {mb_done:.1f} / {total_mb:.1f} MB ({pct}%)"
            else:
                msg = f"Downloading ffmpeg... {mb_done:.1f} MB"
            self.after(0, lambda m=msg: self.lbl_ffmpeg_status.config(text=m, fg=BLUE))

        def run():
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name
                urllib.request.urlretrieve(FFMPEG_RELEASE_URL, tmp_path, reporthook)
                _status("Extracting ffmpeg...", BLUE)
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    for member in zf.namelist():
                        fname = member.split("/")[-1]
                        if fname in ("ffmpeg.exe", "ffprobe.exe"):
                            data = zf.read(member)
                            out = dest_dir / fname
                            out.write_bytes(data)
                os.unlink(tmp_path)
                ffmpeg_exe = str(dest_dir / "ffmpeg.exe")
                self.after(0, lambda: self._set_ffmpeg_path(ffmpeg_exe))
            except Exception as exc:
                _status(f"Download failed: {exc}", LOG_RED)
            finally:
                self.after(0, lambda: self.btn_get_ffmpeg.config(
                    state="normal", text="↓ Get ffmpeg"))

        threading.Thread(target=run, daemon=True).start()

    # ── Quick Setup ────────────────────────────────────────────────────────────
    def _quick_setup(self):
        self.btn_quick_setup.config(state="disabled", text="Setting up...")
        self.btn_get_ytdlp.config(state="disabled")
        self.btn_get_ffmpeg.config(state="disabled")

        import threading as _t
        lock = _t.Lock()
        done = [0]

        def on_both_done():
            with lock:
                done[0] += 1
                if done[0] < 2:
                    return
            def re_enable():
                self.btn_quick_setup.config(
                    state="normal",
                    text="⚡  Quick Setup  —  download yt-dlp + ffmpeg")
                self.btn_get_ytdlp.config(state="normal")
                self.btn_get_ffmpeg.config(state="normal")
            self.after(0, re_enable)

        def dl_ytdlp():
            dest_dir = _BASE / "yt-dlp"
            dest_file = dest_dir / "yt-dlp.exe"

            def rh(count, block_size, total_size):
                mb = count * block_size / 1_048_576
                if total_size > 0:
                    pct = min(100, count * block_size * 100 // total_size)
                    msg = f"Downloading yt-dlp... {mb:.1f}/{total_size/1_048_576:.1f} MB ({pct}%)"
                else:
                    msg = f"Downloading yt-dlp... {mb:.1f} MB"
                self.after(0, lambda m=msg: self.lbl_ytdlp_status.config(text=m, fg=BLUE))

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(YTDLP_RELEASE_URL, str(dest_file), rh)
                self.after(0, lambda: self._set_ytdlp_path(str(dest_file)))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self.lbl_ytdlp_status.config(
                    text=f"yt-dlp download failed: {e}", fg=LOG_RED))
            finally:
                on_both_done()

        def dl_ffmpeg():
            dest_dir = _BASE / "ffmpeg"

            def _st(text, color):
                self.after(0, lambda t=text, c=color: self.lbl_ffmpeg_status.config(text=t, fg=c))

            def rh(count, block_size, total_size):
                mb = count * block_size / 1_048_576
                if total_size > 0:
                    pct = min(100, count * block_size * 100 // total_size)
                    msg = f"Downloading ffmpeg... {mb:.1f}/{total_size/1_048_576:.1f} MB ({pct}%)"
                else:
                    msg = f"Downloading ffmpeg... {mb:.1f} MB"
                self.after(0, lambda m=msg: self.lbl_ffmpeg_status.config(text=m, fg=BLUE))

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name
                urllib.request.urlretrieve(FFMPEG_RELEASE_URL, tmp_path, rh)
                _st("Extracting ffmpeg...", BLUE)
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    for member in zf.namelist():
                        fname = member.split("/")[-1]
                        if fname in ("ffmpeg.exe", "ffprobe.exe"):
                            (dest_dir / fname).write_bytes(zf.read(member))
                os.unlink(tmp_path)
                ffmpeg_exe = str(dest_dir / "ffmpeg.exe")
                self.after(0, lambda: self._set_ffmpeg_path(ffmpeg_exe))
            except Exception as exc:
                _st(f"ffmpeg download failed: {exc}", LOG_RED)
            finally:
                on_both_done()

        threading.Thread(target=dl_ytdlp, daemon=True).start()
        threading.Thread(target=dl_ffmpeg, daemon=True).start()

    # ── App self-update ────────────────────────────────────────────────────────
    def _check_app_update(self):
        self.btn_check_update.config(state="disabled", text="Checking...")
        self.lbl_update_status.config(text="Checking for updates...", fg=FG1)

        def _status(text, color):
            self.after(0, lambda t=text, c=color: self.lbl_update_status.config(text=t, fg=c))

        def run():
            try:
                req = urllib.request.Request(
                    APP_RELEASES_API,
                    headers={"User-Agent": f"dlp-ui/{VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())

                latest_tag = data.get("tag_name", "").lstrip("v")
                assets = data.get("assets", [])
                exe_asset = next((a for a in assets if a["name"] == "dlp-ui.exe"), None)

                if not exe_asset:
                    _status("No dlp-ui.exe asset found in latest release.", LOG_WARN)
                    return

                if _parse_ver(latest_tag) <= _parse_ver(VERSION):
                    _status(f"✓ v{VERSION} — already up to date", LOG_OK)
                    return

                dl_url = exe_asset["browser_download_url"]
                _status(
                    f"Update available: v{VERSION} → v{latest_tag}  —  click the button to install",
                    LOG_WARN,
                )
                self.after(0, lambda u=dl_url, v=latest_tag: self._offer_update(u, v))
            except Exception as exc:
                _status(f"Could not check for updates: {exc}", LOG_RED)
            finally:
                self.after(0, lambda: self.btn_check_update.config(
                    state="normal", text="Check for Updates",
                    command=self._check_app_update))

        threading.Thread(target=run, daemon=True).start()

    def _offer_update(self, download_url: str, new_ver: str):
        self.btn_check_update.config(
            state="normal",
            text=f"↓  Install v{new_ver}",
            command=lambda: self._download_and_apply_update(download_url, new_ver),
        )

    def _download_and_apply_update(self, download_url: str, new_ver: str):
        if not getattr(sys, "frozen", False):
            self.lbl_update_status.config(
                text="Self-update only works in the compiled EXE, not from source.",
                fg=LOG_WARN)
            return

        self.btn_check_update.config(state="disabled", text="Downloading...")

        def _status(text, color):
            self.after(0, lambda t=text, c=color: self.lbl_update_status.config(text=t, fg=c))

        def reporthook(count, block_size, total_size):
            mb = count * block_size / 1_048_576
            if total_size > 0:
                pct  = min(100, count * block_size * 100 // total_size)
                tmb  = total_size / 1_048_576
                msg  = f"Downloading v{new_ver}... {mb:.1f}/{tmb:.1f} MB ({pct}%)"
            else:
                msg = f"Downloading v{new_ver}... {mb:.1f} MB"
            self.after(0, lambda m=msg: self.lbl_update_status.config(text=m, fg=BLUE))

        def run():
            current  = Path(sys.executable)
            new_file = current.with_name("dlp-ui-update.exe")
            bat_file = current.with_name("_dlp-ui-updater.bat")
            try:
                urllib.request.urlretrieve(download_url, str(new_file), reporthook)

                bat_file.write_text(
                    "@echo off\r\n"
                    "ping -n 3 127.0.0.1 > nul\r\n"
                    f'move /y "{new_file}" "{current}"\r\n'
                    f'start "" "{current}"\r\n'
                    "del \"%~f0\"\r\n",
                    encoding="utf-8",
                )

                _status(f"v{new_ver} downloaded — restarting app...", LOG_OK)
                self.after(800, lambda: self._apply_update(bat_file))
            except Exception as exc:
                _status(f"Update failed: {exc}", LOG_RED)
                self.after(0, lambda: self.btn_check_update.config(
                    state="normal", text="Check for Updates",
                    command=self._check_app_update))

        threading.Thread(target=run, daemon=True).start()

    def _apply_update(self, bat_file: Path):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["cmd", "/c", str(bat_file)], creationflags=flags)
        self.on_close()

    # ── Format change ──────────────────────────────────────────────────────────
    def _fmt_changed(self, _=None):
        t = FORMAT_TYPES[self.cbo_fmt.get()]
        qs = list(AUDIO_QUALITIES) if t == "audio" else list(VIDEO_QUALITIES)
        self.cbo_qual.config(values=qs)
        self.cbo_qual.current(0)

    # ── Log helpers ────────────────────────────────────────────────────────────
    def _log(self, text, tag="gray"):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _poll(self):
        try:
            while True:
                item = self._q.get_nowait()
                if item is None:
                    self._on_done()
                else:
                    text, tag = item
                    self._log(text, tag)
        except queue.Empty:
            pass
        self.after(200, self._poll)

    def _on_done(self):
        if self.proc is not None:
            ec = self.proc.returncode
            self.proc = None
            if ec == 0:
                self._log("Done — download complete.", "ok")
            else:
                self._log(f"Failed — exit code {ec}.", "fail")
        self._log("")
        self.btn_dl.config(state="normal", text="Download")

    # ── Browse ─────────────────────────────────────────────────────────────────
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.txt_dest.get())
        if d:
            self.txt_dest.delete(0, "end")
            self.txt_dest.insert(0, d)

    # ── Download ───────────────────────────────────────────────────────────────
    def _start(self):
        url  = self.txt_url.value()
        dest = self.txt_dest.get().strip()
        fmt  = self.cbo_fmt.get()
        qual = self.cbo_qual.get()

        if not url:
            messagebox.showwarning("Missing URL", "Please paste a URL first.")
            return
        if not os.path.isdir(dest):
            messagebox.showwarning("Bad path", "Destination folder does not exist.")
            return
        if not self.ytdlp_path or not os.path.isfile(self.ytdlp_path):
            messagebox.showerror(
                "yt-dlp not found",
                "yt-dlp.exe could not be located.\n\n"
                "Go to Settings → Dependencies and use Browse or Auto-detect.",
            )
            return

        s = {
            "embed_thumbnail":  self.v_thumb.get(),
            "embed_metadata":   self.v_meta.get(),
            "embed_chapters":   self.v_chapters.get(),
            "sponsorblock":     self.v_sponsor.get(),
            "remux_to":         self.cbo_remux.get(),
            "recode_to":        self.cbo_recode.get(),
            "write_subs":       self.v_subs.get(),
            "write_auto_subs":  self.v_auto_subs.get(),
            "sub_langs":        self.txt_sub_langs.get().strip(),
            "rate_limit":       self.txt_rate.get().strip(),
            "concurrent_frags": int(self.spn_frags.get()),
            "cookies":          self.cbo_cookies.get(),
            "retries":          int(self.spn_retries.get()),
            "proxy":            self.txt_proxy.get().strip(),
            "playlist_mode":    self.v_playlist.get(),
            "out_template":     self.txt_tmpl.get().strip() or "%(title)s.%(ext)s",
            "extra_args":       self.txt_extra.get().strip(),
        }

        args = build_args(fmt, qual, dest, url, s)

        if s["recode_to"] and s["recode_to"] != "None":
            args = ["--recode-video", s["recode_to"].lower()] + args

        args += ["--retries", str(s["retries"])]

        if s["proxy"]:
            args += ["--proxy", s["proxy"]]

        tmpl = s["out_template"]
        if tmpl and tmpl != "%(title)s.%(ext)s":
            try:
                i = args.index("-o")
                args[i + 1] = os.path.join(dest, tmpl)
            except ValueError:
                pass

        extra = s["extra_args"]
        if extra:
            try:
                args += shlex.split(extra)
            except ValueError:
                args += extra.split()

        self.btn_dl.config(state="disabled", text="Downloading...")
        self._log(f"Starting: {url}", "blue")
        self._log(f"  Format  : {fmt} | {qual}", "gray")
        self._log(f"  Dest    : {dest}", "gray")
        self._log("")

        ffmpeg_dir = str(Path(self.ffmpeg_path).parent) if self.ffmpeg_path and os.path.isfile(self.ffmpeg_path) else ""
        if ffmpeg_dir and not shutil.which("ffmpeg"):
            args = ["--ffmpeg-location", ffmpeg_dir] + args

        cmd = [self.ytdlp_path] + args

        _STALE_HINTS = [
            "nsig extraction failed",
            "Precondition check failed",
            "Only images are available",
        ]

        def run():
            stale_detected = False
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                )
                for line in self.proc.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    if any(h in line for h in _STALE_HINTS):
                        stale_detected = True
                    if "ERROR" in line or line.startswith("ERR:"):
                        tag = "err"
                    elif "[download]" in line:
                        tag = "dl"
                    elif any(x in line for x in ("[info]", "[youtube]", "[generic]")):
                        tag = "info"
                    else:
                        tag = "gray"
                    self._q.put((line, tag))
                self.proc.wait()
                if stale_detected and self.proc.returncode != 0:
                    self._q.put(("", "gray"))
                    self._q.put(("  Hint: yt-dlp could not decrypt YouTube's player.", "info"))
                    self._q.put(("  Go to Settings → Dependencies → ↑ Update yt-dlp", "info"))
            except Exception as exc:
                self._q.put((f"Error launching yt-dlp: {exc}", "err"))
            finally:
                self._q.put(None)

        threading.Thread(target=run, daemon=True).start()

    def on_close(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

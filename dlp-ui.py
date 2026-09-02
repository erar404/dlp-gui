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
from pathlib import Path

# ── Config persistence ─────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent

CONFIG_FILE = _BASE / "dlp-ui-config.json"

YTDLP_RELEASE_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
)

COMMON_YTDLP_PATHS = [
    r"C:\ERAR\yt-dlp\dist\yt-dlp.exe",
    r"C:\Program Files\yt-dlp\yt-dlp.exe",
    r"C:\Program Files (x86)\yt-dlp\yt-dlp.exe",
    str(Path.home() / "yt-dlp" / "yt-dlp.exe"),
    str(Path.home() / "AppData" / "Local" / "Programs" / "yt-dlp" / "yt-dlp.exe"),
    str(Path.home() / "AppData" / "Local" / "yt-dlp" / "yt-dlp.exe"),
    str(_BASE / "yt-dlp.exe"),
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


def find_ytdlp() -> str:
    """Return the first valid yt-dlp executable path, or empty string."""
    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found
    for p in COMMON_YTDLP_PATHS:
        if os.path.isfile(p):
            return p
    return ""


_cfg = _load_config()
YT_DLP = _cfg.get("ytdlp_path") or find_ytdlp()

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
        self.geometry("660x700")
        self.resizable(False, False)
        self.configure(bg=BG0)
        self.proc = None
        self._q = queue.Queue()
        self.ytdlp_path = YT_DLP
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

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_dl  = tk.Frame(nb, bg=BG0)
        self.tab_cfg = tk.Frame(nb, bg=BG0)
        nb.add(self.tab_dl,  text="  Download  ")
        nb.add(self.tab_cfg, text="  Settings  ")

        self._build_download()
        self._build_settings()

    # ── Widget helpers ─────────────────────────────────────────────────────────
    def _lbl(self, p, text, x, y):
        tk.Label(p, text=text, bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=x, y=y)

    def _entry(self, p, x, y, w, ph=None):
        e = PlaceholderEntry(p, placeholder=ph or "",
                             bg=BG2, fg=FG0, insertbackground=FG0,
                             relief="solid", bd=1, font=("Segoe UI", 9))
        e.place(x=x, y=y, width=w, height=28)
        return e

    def _plain_entry(self, p, x, y, w, default=""):
        e = tk.Entry(p, bg=BG2, fg=FG0, insertbackground=FG0,
                     relief="solid", bd=1, font=("Segoe UI", 9))
        e.place(x=x, y=y, width=w, height=28)
        if default:
            e.insert(0, default)
        return e

    def _combo(self, p, x, y, w, values):
        c = ttk.Combobox(p, values=values, state="readonly", font=("Segoe UI", 9))
        c.place(x=x, y=y, width=w, height=26)
        c.current(0)
        return c

    def _btn(self, p, text, x, y, w, h, bg, fg, border, cmd, font=None):
        b = tk.Button(p, text=text, bg=bg, fg=fg, relief="flat", bd=0,
                      cursor="hand2", font=font or ("Segoe UI", 9), command=cmd,
                      highlightthickness=1, highlightbackground=border,
                      activebackground=BG3, activeforeground=FG0)
        b.place(x=x, y=y, width=w, height=h)
        return b

    def _check(self, p, text, x, y):
        var = tk.BooleanVar()
        tk.Checkbutton(p, text=text, variable=var, bg=BG0, fg=FG1,
                       selectcolor=BG2, activebackground=BG0, activeforeground=FG0,
                       font=("Segoe UI", 9)).place(x=x, y=y)
        return var

    def _group(self, p, text, x, y, w, h):
        f = tk.LabelFrame(p, text=text, bg=BG0, fg=FG2,
                          bd=1, relief="groove", font=("Segoe UI", 9))
        f.place(x=x, y=y, width=w, height=h)
        return f

    def _spinbox(self, p, x, y, w, lo, hi, default):
        s = tk.Spinbox(p, from_=lo, to=hi, bg=BG2, fg=FG0,
                       insertbackground=FG0, buttonbackground=BG3,
                       relief="solid", bd=1, font=("Segoe UI", 9))
        s.place(x=x, y=y, width=w, height=26)
        s.delete(0, "end")
        s.insert(0, str(default))
        return s

    # ── Download tab ───────────────────────────────────────────────────────────
    def _build_download(self):
        p = self.tab_dl

        self._lbl(p, "YouTube / Video URL", 16, 16)
        self.txt_url = self._entry(p, 16, 38, 618, "Paste a link here...")

        self._lbl(p, "Format", 16, 82)
        self._lbl(p, "Quality / Resolution", 320, 82)
        self.cbo_fmt  = self._combo(p, 16, 102, 296, list(FORMAT_TYPES))
        self.cbo_qual = self._combo(p, 320, 102, 314, list(VIDEO_QUALITIES))
        self.cbo_fmt.bind("<<ComboboxSelected>>", self._fmt_changed)

        self._lbl(p, "Destination Folder", 16, 148)
        self.txt_dest = self._plain_entry(p, 16, 168, 522,
                                          str(Path.home() / "Videos"))
        self._btn(p, "Browse...", 546, 167, 88, 30, BG2, FG0, BG3, self._browse)

        self.btn_dl = self._btn(p, "Download", 16, 212, 618, 44,
                                RED, FG0, RED, self._start,
                                font=("Segoe UI Semibold", 11))

        self._lbl(p, "Output Log", 16, 270)
        self.log = tk.Text(p, bg="#0a0a0a", fg=LOG_GRAY, state="disabled",
                           relief="flat", bd=0, wrap="word",
                           font=self._mono())
        self.log.place(x=16, y=290, width=618, height=300)

        sb = tk.Scrollbar(p, command=self.log.yview, bg=BG2, troughcolor=BG1,
                          activebackground=BG3)
        sb.place(x=634, y=290, width=12, height=300)
        self.log.config(yscrollcommand=sb.set)

        for tag, color in [("err",  LOG_RED),   ("dl",   LOG_GREEN),
                            ("info", BLUE),       ("gray", LOG_GRAY),
                            ("blue", BLUE),       ("ok",   LOG_OK),
                            ("fail", LOG_FAIL)]:
            self.log.tag_configure(tag, foreground=color)

        self._btn(p, "Clear log", 16, 597, 618, 24, BG1, FG2, BG2,
                  self._clear, font=("Segoe UI", 8))

    def _mono(self):
        try:
            import tkinter.font as tkf
            return ("Cascadia Code", 8) if "Cascadia Code" in tkf.families() else ("Consolas", 9)
        except Exception:
            return ("Consolas", 9)

    # ── Settings tab ──────────────────────────────────────────────────────────
    def _build_settings(self):
        p = self.tab_cfg

        # yt-dlp Executable
        g = self._group(p, "yt-dlp Executable", 10, 10, 630, 62)
        self.txt_ytdlp = self._plain_entry(g, 0, 4, 290, self.ytdlp_path)
        self._btn(g, "Browse...", 296, 4, 74, 26, BG2, FG0, BG3,
                  self._browse_ytdlp)
        self._btn(g, "Auto-detect", 376, 4, 84, 26, BG2, FG0, BG3,
                  self._autodetect_ytdlp)
        self.btn_get_ytdlp = self._btn(g, "↓ Get yt-dlp", 466, 4, 140, 26,
                                        BG2, FG0, BG3, self._download_ytdlp)
        self.lbl_ytdlp_status = tk.Label(g, text="", bg=BG0,
                                          font=("Segoe UI", 8))
        self.lbl_ytdlp_status.place(x=0, y=34)
        self.txt_ytdlp.bind("<FocusOut>", self._on_ytdlp_entry_change)
        self.txt_ytdlp.bind("<Return>",   self._on_ytdlp_entry_change)
        self._refresh_ytdlp_status()

        # Post-Processing
        g = self._group(p, "Post-Processing", 10, 82, 630, 115)
        self.v_thumb    = self._check(g, "Embed thumbnail as cover art",              0,   4)
        self.v_meta     = self._check(g, "Embed metadata (title, artist...)",         0,  28)
        self.v_chapters = self._check(g, "Embed chapter markers",                     0,  52)
        self.v_sponsor  = self._check(g, "SponsorBlock: remove sponsored segments",   290,  4)
        tk.Label(g, text="Remux to:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=290, y=30)
        self.cbo_remux  = self._combo(g, 355, 26, 130,
                                      ["None","mp4","mkv","mov","webm","avi","flv"])
        tk.Label(g, text="Re-encode to:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=290, y=58)
        self.cbo_recode = self._combo(g, 383, 54, 102,
                                      ["None","mp4","mkv","mov","webm","mp3","m4a","wav"])

        # Subtitles
        g = self._group(p, "Subtitles", 10, 207, 630, 88)
        self.v_subs      = self._check(g, "Download subtitles",               0,  4)
        self.v_auto_subs = self._check(g, "Include auto-generated subtitles", 0, 28)
        tk.Label(g, text="Languages (comma-separated, e.g. en,ja):",
                 bg=BG0, fg=FG1, font=("Segoe UI", 9)).place(x=270, y=6)
        self.txt_sub_langs = self._plain_entry(g, 270, 26, 200, "en")

        # Network
        g = self._group(p, "Network", 10, 305, 630, 112)
        tk.Label(g, text="Rate limit (e.g. 5M, 500K, blank=off):",
                 bg=BG0, fg=FG1, font=("Segoe UI", 9)).place(x=0, y=6)
        self.txt_rate    = self._plain_entry(g, 0, 26, 150)
        tk.Label(g, text="Concurrent fragments:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=168, y=6)
        self.spn_frags   = self._spinbox(g, 168, 26, 72, 1, 32, 1)
        tk.Label(g, text="Cookies from browser:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=258, y=6)
        self.cbo_cookies = self._combo(g, 258, 26, 180,
            ["None","chrome","firefox","edge","brave","opera","safari","vivaldi","chromium"])
        tk.Label(g, text="Retries:", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=456, y=6)
        self.spn_retries = self._spinbox(g, 456, 26, 60, 1, 50, 10)
        tk.Label(g, text="Proxy (e.g. socks5://127.0.0.1:1080):", bg=BG0, fg=FG1,
                 font=("Segoe UI", 9)).place(x=0, y=62)
        self.txt_proxy   = self._plain_entry(g, 228, 58, 290)

        # Playlist
        g = self._group(p, "Playlist Handling", 10, 427, 630, 64)
        self.v_playlist = tk.StringVar(value="auto")
        for text, val, x in [
            ("Auto (let yt-dlp decide)", "auto",   0),
            ("Single video only",        "single", 200),
            ("Always download full playlist", "full", 370),
        ]:
            tk.Radiobutton(g, text=text, variable=self.v_playlist, value=val,
                           bg=BG0, fg=FG1, selectcolor=BG2,
                           activebackground=BG0, activeforeground=FG0,
                           font=("Segoe UI", 9)).place(x=x, y=6)

        # Output template
        g = self._group(p, "Output Filename Template", 10, 501, 630, 64)
        tk.Label(g, text="Template (yt-dlp format, %(title)s.%(ext)s = default):",
                 bg=BG0, fg=FG1, font=("Segoe UI", 9)).place(x=0, y=2)
        self.txt_tmpl = self._plain_entry(g, 0, 22, 606, "%(title)s.%(ext)s")

        # Extra args
        g = self._group(p, "Extra yt-dlp Arguments", 10, 575, 630, 56)
        tk.Label(g, text="Any additional flags appended verbatim:",
                 bg=BG0, fg=FG1, font=("Segoe UI", 9)).place(x=0, y=2)
        self.txt_extra = self._plain_entry(g, 0, 20, 606)

    # ── yt-dlp path helpers ────────────────────────────────────────────────────
    def _refresh_ytdlp_status(self):
        path = self.ytdlp_path
        if path and os.path.isfile(path):
            self.lbl_ytdlp_status.config(text=f"Found: {path}", fg=LOG_OK)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↑ Update yt-dlp")
        elif path:
            self.lbl_ytdlp_status.config(text=f"Not found: {path}", fg=LOG_RED)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↓ Get yt-dlp")
        else:
            self.lbl_ytdlp_status.config(text="No path set — use Browse or ↓ Get yt-dlp", fg=FG2)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↓ Get yt-dlp")

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
                "Go to Settings → yt-dlp Executable and use Browse or Auto-detect.",
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

        cmd = [self.ytdlp_path] + args

        def run():
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

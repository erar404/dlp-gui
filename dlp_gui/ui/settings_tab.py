"""Settings tab: dependency management (yt-dlp/ffmpeg/Python + Spleeter
audio tools), download post-processing options, and app self-update.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..constants import APP_RELEASES_API, VERSION
from ..dependencies import (
    EMBED_PYTHON_URL, FFMPEG_RELEASE_URL, GET_PIP_URL, YTDLP_RELEASE_URL,
    check_librosa_installed, check_spleeter_installed, find_ffmpeg,
    find_python, find_ytdlp,
)
from ..paths import BASE, load_config, parse_version, save_config
from ..theme import (
    BG0, BG2, BG3, BLUE, FG0, FG1, FG2, LOG_OK, LOG_RED, LOG_WARN,
)


def _no_window_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class SettingsTabMixin:
    """Adds the Settings tab and its behavior to the main App window."""

    # ── UI construction ───────────────────────────────────────────────
    def _build_settings(self):
        p = self.tab_cfg
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)

        # ── Scrollable canvas ────────────────────────────────────────
        self._cfg_canvas = canvas = tk.Canvas(
            p, bg=BG0, highlightthickness=0)
        vsb = tk.Scrollbar(
            p, orient="vertical", command=canvas.yview, bg=BG2,
            troughcolor=BG3, activebackground=BG3)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="NS")
        canvas.grid(row=0, column=0, sticky="NSEW")

        inner = tk.Frame(canvas, bg=BG0)
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        inner.columnconfigure(0, weight=1)

        widgets = _SettingsWidgetFactory(inner)

        self._build_dependencies_group(widgets)
        self._build_audio_tools_group(widgets)
        self._build_post_processing_group(widgets)
        self._build_subtitles_group(widgets)
        self._build_network_group(widgets)
        self._build_playlist_group(widgets)
        self._build_output_template_group(widgets)
        self._build_extra_args_group(widgets)
        self._build_app_update_group(widgets, inner)

    # ── Dependencies group ─────────────────────────────────────────────
    def _build_dependencies_group(self, w):
        g = w.grp("Dependencies")
        g.columnconfigure(1, weight=1)

        tk.Label(
            g, text="yt-dlp:", bg=BG0, fg=FG1, font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, padx=(8, 4), pady=(10, 3), sticky="W")
        self.txt_ytdlp = w.ent(g, self.ytdlp_path)
        self.txt_ytdlp.grid(
            row=0, column=1, padx=4, pady=(10, 3), sticky="EW", ipady=3)
        w.sbtn(g, "Browse", self._browse_ytdlp).grid(
            row=0, column=2, padx=4, pady=(10, 3), ipady=3)
        w.sbtn(g, "Auto-detect", self._autodetect_ytdlp).grid(
            row=0, column=3, padx=4, pady=(10, 3), ipady=3)
        self.btn_get_ytdlp = w.sbtn(
            g, "↓ Get yt-dlp", self._download_ytdlp)
        self.btn_get_ytdlp.grid(
            row=0, column=4, padx=(4, 8), pady=(10, 3), ipady=3)

        self.lbl_ytdlp_status = w.slbl(g)
        self.lbl_ytdlp_status.grid(
            row=1, column=0, columnspan=5, padx=8, pady=(0, 4), sticky="EW")

        tk.Label(
            g, text="ffmpeg:", bg=BG0, fg=FG1, font=("Segoe UI", 9, "bold"),
        ).grid(row=2, column=0, padx=(8, 4), pady=(4, 3), sticky="W")
        self.txt_ffmpeg = w.ent(g, self.ffmpeg_path)
        self.txt_ffmpeg.grid(
            row=2, column=1, padx=4, pady=(4, 3), sticky="EW", ipady=3)
        w.sbtn(g, "Browse", self._browse_ffmpeg).grid(
            row=2, column=2, padx=4, pady=(4, 3), ipady=3)
        w.sbtn(g, "Auto-detect", self._autodetect_ffmpeg).grid(
            row=2, column=3, padx=4, pady=(4, 3), ipady=3)
        self.btn_get_ffmpeg = w.sbtn(
            g, "↓ Get ffmpeg", self._download_ffmpeg)
        self.btn_get_ffmpeg.grid(
            row=2, column=4, padx=(4, 8), pady=(4, 3), ipady=3)

        self.lbl_ffmpeg_status = w.slbl(g)
        self.lbl_ffmpeg_status.grid(
            row=3, column=0, columnspan=5, padx=8, pady=(0, 4), sticky="EW")

        self.btn_quick_setup = tk.Button(
            g, text="⚡  Quick Setup  —  download yt-dlp + ffmpeg",
            bg=BG2, fg=BLUE, relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9), command=self._quick_setup,
            highlightthickness=1, highlightbackground=BLUE,
            activebackground=BG3, activeforeground=FG0)
        self.btn_quick_setup.grid(
            row=4, column=0, columnspan=5, padx=8, pady=(2, 8),
            sticky="EW", ipady=3)

        self.txt_ytdlp.bind("<FocusOut>", self._on_ytdlp_entry_change)
        self.txt_ytdlp.bind("<Return>", self._on_ytdlp_entry_change)
        self.txt_ffmpeg.bind("<FocusOut>", self._on_ffmpeg_entry_change)
        self.txt_ffmpeg.bind("<Return>", self._on_ffmpeg_entry_change)
        self._refresh_ytdlp_status()
        self._refresh_ffmpeg_status()

    # ── Audio Tools group ──────────────────────────────────────────────
    def _build_audio_tools_group(self, w):
        g = w.grp("Audio Tools (Spleeter · Click Track · Tempo)")
        g.columnconfigure(0, weight=1)

        tk.Label(
            g, text=(
                "MP3 downloads can optionally be split into isolated "
                "stems (vocals, drums, bass, etc.) using Deezer's "
                "Spleeter AI model, and analyzed with librosa to show "
                "the suggested tempo (BPM) and/or generate a click "
                "track at the detected beat."
            ), bg=BG0, fg=FG2, font=("Segoe UI", 8), justify="left",
            wraplength=560,
        ).grid(row=0, column=0, padx=8, pady=(10, 6), sticky="W")

        self.btn_setup_spleeter = tk.Button(
            g, text="⚡  Auto-Setup Audio Tools  —  no Python install "
                    "needed",
            bg=BG2, fg=BLUE, relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9), command=self._setup_embedded_python,
            highlightthickness=1, highlightbackground=BLUE,
            activebackground=BG3, activeforeground=FG0)
        self.btn_setup_spleeter.grid(
            row=1, column=0, padx=8, pady=(0, 4), sticky="EW", ipady=3)

        self.lbl_spleeter_status = w.slbl(g)
        self.lbl_spleeter_status.grid(
            row=2, column=0, padx=8, pady=(0, 8), sticky="EW")

        adv = tk.LabelFrame(
            g, text="Advanced — use an existing Python interpreter "
                    "instead",
            bg=BG0, fg=FG2, bd=1, relief="groove", font=("Segoe UI", 8))
        adv.grid(row=3, column=0, padx=8, pady=(0, 10), sticky="EW")
        adv.columnconfigure(0, weight=1)

        row = tk.Frame(adv, bg=BG0)
        row.grid(row=0, column=0, padx=6, pady=6, sticky="EW")
        row.columnconfigure(0, weight=1)
        self.txt_python = w.ent(row, self.python_path)
        self.txt_python.grid(row=0, column=0, sticky="EW", ipady=3)
        w.sbtn(row, "Browse", self._browse_python).grid(
            row=0, column=1, padx=(4, 0), ipady=3)
        w.sbtn(row, "Auto-detect", self._autodetect_python).grid(
            row=0, column=2, padx=(4, 0), ipady=3)
        self.btn_install_spleeter = w.sbtn(
            row, "↓ Install Spleeter", self._install_spleeter)
        self.btn_install_spleeter.grid(row=0, column=3, padx=(4, 0), ipady=3)

        tk.Label(
            adv, text=(
                "Must be Python 3.6–3.10 — newer versions can't build "
                "Spleeter's dependencies."
            ), bg=BG0, fg=FG2, font=("Segoe UI", 8), justify="left",
            wraplength=540,
        ).grid(row=1, column=0, padx=6, pady=(0, 6), sticky="W")

        self.txt_python.bind("<FocusOut>", self._on_python_entry_change)
        self.txt_python.bind("<Return>", self._on_python_entry_change)
        self._refresh_spleeter_status()

    # ── Post-Processing group ───────────────────────────────────────────
    def _build_post_processing_group(self, w):
        g = w.grp("Post-Processing")
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)

        cb, self.v_thumb = w.chk(g, "Embed thumbnail as cover art")
        cb.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="W")
        cb, self.v_meta = w.chk(g, "Embed metadata (title, artist...)")
        cb.grid(row=1, column=0, padx=8, pady=2, sticky="W")
        cb, self.v_chapters = w.chk(g, "Embed chapter markers")
        cb.grid(row=2, column=0, padx=8, pady=(2, 8), sticky="W")

        cb, self.v_sponsor = w.chk(
            g, "SponsorBlock: remove sponsored segments")
        cb.grid(row=0, column=1, padx=8, pady=(8, 2), sticky="W")

        rr = tk.Frame(g, bg=BG0)
        rr.grid(row=1, column=1, rowspan=2, padx=8, pady=(2, 8), sticky="EW")
        rr.columnconfigure(1, weight=1)
        w.lbl10(rr, "Remux to:").grid(
            row=0, column=0, padx=(0, 6), pady=3, sticky="W")
        self.cbo_remux = w.cbo(
            rr, ["None", "mp4", "mkv", "mov", "webm", "avi", "flv"])
        self.cbo_remux.grid(row=0, column=1, sticky="EW", ipady=2)
        w.lbl10(rr, "Re-encode to:").grid(
            row=1, column=0, padx=(0, 6), pady=3, sticky="W")
        self.cbo_recode = w.cbo(
            rr, ["None", "mp4", "mkv", "mov", "webm", "mp3", "m4a", "wav"])
        self.cbo_recode.grid(row=1, column=1, sticky="EW", ipady=2)

    # ── Subtitles group ──────────────────────────────────────────────────
    def _build_subtitles_group(self, w):
        g = w.grp("Subtitles")
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)

        cb, self.v_subs = w.chk(g, "Download subtitles")
        cb.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="W")
        cb, self.v_auto_subs = w.chk(g, "Include auto-generated subtitles")
        cb.grid(row=1, column=0, padx=8, pady=(2, 8), sticky="W")

        sr = tk.Frame(g, bg=BG0)
        sr.grid(row=0, column=1, rowspan=2, padx=8, pady=8, sticky="EW")
        sr.columnconfigure(0, weight=1)
        w.lbl10(sr, "Languages (comma-separated, e.g. en,ja):").grid(
            row=0, column=0, sticky="W", pady=(0, 3))
        self.txt_sub_langs = w.ent(sr, "en")
        self.txt_sub_langs.grid(row=1, column=0, sticky="EW", ipady=3)

    # ── Network group ────────────────────────────────────────────────────
    def _build_network_group(self, w):
        g = w.grp("Network")
        g.columnconfigure(0, weight=1)

        top = tk.Frame(g, bg=BG0)
        top.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="EW")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(2, weight=1)

        w.lbl10(top, "Rate limit (e.g. 5M, 500K):").grid(
            row=0, column=0, sticky="W")
        self.txt_rate = w.ent(top)
        self.txt_rate.grid(row=1, column=0, sticky="EW", ipady=3)

        w.lbl10(top, "Concurrent frags:").grid(
            row=0, column=1, padx=(12, 4), sticky="W")
        self.spn_frags = w.spn(top, 1, 32, 1)
        self.spn_frags.grid(row=1, column=1, padx=(12, 4), ipady=3)

        w.lbl10(top, "Cookies from browser:").grid(
            row=0, column=2, sticky="W")
        self.cbo_cookies = w.cbo(top, [
            "None", "chrome", "firefox", "edge", "brave", "opera",
            "safari", "vivaldi", "chromium",
        ])
        self.cbo_cookies.grid(row=1, column=2, sticky="EW", ipady=2)

        w.lbl10(top, "Retries:").grid(row=0, column=3, padx=(12, 0), sticky="W")
        self.spn_retries = w.spn(top, 1, 50, 10)
        self.spn_retries.grid(row=1, column=3, padx=(12, 0), ipady=3)

        bot = tk.Frame(g, bg=BG0)
        bot.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="EW")
        bot.columnconfigure(0, weight=1)
        w.lbl10(bot, "Proxy (e.g. socks5://127.0.0.1:1080):").grid(
            row=0, column=0, sticky="W", pady=(0, 3))
        self.txt_proxy = w.ent(bot)
        self.txt_proxy.grid(row=1, column=0, sticky="EW", ipady=3)

    # ── Playlist group ───────────────────────────────────────────────────
    def _build_playlist_group(self, w):
        g = w.grp("Playlist Handling")
        g.columnconfigure(0, weight=1)

        self.v_playlist = tk.StringVar(value="auto")
        pl = tk.Frame(g, bg=BG0)
        pl.grid(row=0, column=0, padx=8, pady=8, sticky="W")
        for text, val in [
            ("Auto (let yt-dlp decide)", "auto"),
            ("Single video only", "single"),
            ("Always full playlist", "full"),
        ]:
            tk.Radiobutton(
                pl, text=text, variable=self.v_playlist, value=val,
                bg=BG0, fg=FG1, selectcolor=BG2,
                activebackground=BG0, activeforeground=FG0,
                font=("Segoe UI", 10),
            ).pack(side="left", padx=(0, 16))

    # ── Output template group ───────────────────────────────────────────
    def _build_output_template_group(self, w):
        g = w.grp("Output Filename Template")
        g.columnconfigure(0, weight=1)

        w.lbl10(g, "Template (%(title)s.%(ext)s = default):").grid(
            row=0, column=0, padx=8, pady=(8, 3), sticky="W")
        self.txt_tmpl = w.ent(g, "%(title)s.%(ext)s")
        self.txt_tmpl.grid(
            row=1, column=0, padx=8, pady=(0, 8), sticky="EW", ipady=3)

    # ── Extra args group ─────────────────────────────────────────────────
    def _build_extra_args_group(self, w):
        g = w.grp("Extra yt-dlp Arguments")
        g.columnconfigure(0, weight=1)

        w.lbl10(g, "Any additional flags appended verbatim:").grid(
            row=0, column=0, padx=8, pady=(8, 3), sticky="W")
        self.txt_extra = w.ent(g)
        self.txt_extra.grid(
            row=1, column=0, padx=8, pady=(0, 8), sticky="EW", ipady=3)

    # ── App Update group ─────────────────────────────────────────────────
    def _build_app_update_group(self, w, inner):
        g = w.grp("App Update")
        g.columnconfigure(0, weight=1)

        top_row = tk.Frame(g, bg=BG0)
        top_row.grid(row=0, column=0, padx=8, pady=(8, 3), sticky="EW")
        top_row.columnconfigure(0, weight=1)

        tk.Label(
            top_row, text=f"Current version: v{VERSION}", bg=BG0, fg=FG1,
            font=("Segoe UI", 10),
        ).grid(row=0, column=0, sticky="W")
        self.btn_check_update = w.sbtn(
            top_row, "Check for Updates", self._check_app_update)
        self.btn_check_update.grid(row=0, column=1, padx=(8, 0), ipady=3)

        self.lbl_update_status = w.slbl(g)
        self.lbl_update_status.grid(
            row=1, column=0, padx=8, pady=(0, 8), sticky="EW")

        tk.Frame(inner, bg=BG0, height=8).pack()

    # ── yt-dlp path helpers ──────────────────────────────────────────────
    def _refresh_ytdlp_status(self):
        self._update_dep_banner()
        path = self.ytdlp_path
        if path and os.path.isfile(path):
            self.lbl_ytdlp_status.config(text="Checking version...", fg=FG1)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↑ Update yt-dlp")
            self._check_ytdlp_version()
        elif path:
            self.lbl_ytdlp_status.config(
                text="✗ Not found — verify the path above", fg=LOG_RED)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↓ Get yt-dlp")
        else:
            self.lbl_ytdlp_status.config(
                text="No path set — use Browse or ↓ Get yt-dlp", fg=FG2)
            if hasattr(self, "btn_get_ytdlp"):
                self.btn_get_ytdlp.config(text="↓ Get yt-dlp")

    def _check_ytdlp_version(self):
        path = self.ytdlp_path

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_ytdlp_status.config(
                    text=t, fg=c),
            )

        def run():
            # ── 1. Incomplete file ────────────────────────────────────
            try:
                size = os.path.getsize(path)
            except OSError:
                _status(
                    "⚠ Cannot read file — may be incomplete. Click ↑ "
                    "Update yt-dlp", LOG_RED,
                )
                return
            if size < 1_000_000:
                kb = size // 1024
                _status(
                    f"⚠ File too small ({kb} KB) — incomplete download. "
                    "Click ↑ Update yt-dlp",
                    LOG_RED,
                )
                return

            # ── 2. Runs cleanly ───────────────────────────────────────
            try:
                r = subprocess.run(
                    [path, "--version"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_no_window_flags(),
                )
                local_ver = r.stdout.strip()
                if r.returncode != 0 or not local_ver:
                    _status(
                        "⚠ yt-dlp failed to start — binary may be "
                        "corrupted. Click ↑ Update yt-dlp",
                        LOG_RED,
                    )
                    return
            except Exception as exc:
                _status(f"⚠ Could not run yt-dlp: {exc}", LOG_RED)
                return

            # ── 3. Compare with GitHub latest release ─────────────────
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/yt-dlp/yt-dlp/releases"
                    "/latest",
                    headers={"User-Agent": "dlp-ui/1.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    latest_ver = json.loads(
                        resp.read()).get("tag_name", "").lstrip("v")
            except Exception:
                _status(
                    f"✓ v{local_ver} — could not check for updates "
                    "(offline?)", LOG_OK,
                )
                return

            if parse_version(local_ver) >= parse_version(latest_ver):
                _status(f"✓ v{local_ver} — up to date", LOG_OK)
            else:
                _status(
                    f"⚠ Outdated: v{local_ver} → v{latest_ver} available "
                    "— click ↑ Update yt-dlp",
                    LOG_WARN,
                )

        threading.Thread(target=run, daemon=True).start()

    def _set_ytdlp_path(self, path: str):
        self.ytdlp_path = path
        self.txt_ytdlp.delete(0, "end")
        self.txt_ytdlp.insert(0, path)
        cfg = load_config()
        cfg["ytdlp_path"] = path
        save_config(cfg)
        self._refresh_ytdlp_status()

    def _on_ytdlp_entry_change(self, _=None):
        self._set_ytdlp_path(self.txt_ytdlp.get().strip())

    def _browse_ytdlp(self):
        path = filedialog.askopenfilename(
            title="Locate yt-dlp executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=(
                str(Path(self.ytdlp_path).parent) if self.ytdlp_path
                else str(Path.home())
            ),
        )
        if path:
            self._set_ytdlp_path(path)

    def _autodetect_ytdlp(self):
        found = find_ytdlp()
        if found:
            self._set_ytdlp_path(found)
        else:
            self.lbl_ytdlp_status.config(
                text="Auto-detect failed — use Browse or ↓ Get yt-dlp to "
                     "download it", fg=LOG_RED)

    def _download_ytdlp(self):
        dest_dir = BASE / "yt-dlp"
        dest_file = dest_dir / "yt-dlp.exe"
        action = (
            "Updating"
            if self.ytdlp_path and os.path.isfile(self.ytdlp_path)
            else "Downloading"
        )
        self.btn_get_ytdlp.config(state="disabled", text=f"{action}...")

        def reporthook(count, block_size, total_size):
            mb_done = count * block_size / 1_048_576
            if total_size > 0:
                pct = min(100, count * block_size * 100 // total_size)
                total_mb = total_size / 1_048_576
                msg = (
                    f"Downloading yt-dlp... {mb_done:.1f} / "
                    f"{total_mb:.1f} MB ({pct}%)"
                )
            else:
                msg = f"Downloading yt-dlp... {mb_done:.1f} MB"
            self.after(
                0,
                lambda m=msg: self.lbl_ytdlp_status.config(text=m, fg=BLUE),
            )

        def run():
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(
                    YTDLP_RELEASE_URL, str(dest_file), reporthook)
                self.after(0, lambda: self._set_ytdlp_path(str(dest_file)))
            except Exception as exc:
                self.after(
                    0,
                    lambda e=str(exc): self.lbl_ytdlp_status.config(
                        text=f"Download failed: {e}", fg=LOG_RED),
                )
            finally:
                self.after(
                    0,
                    lambda: self.btn_get_ytdlp.config(
                        state="normal", text="↓ Get yt-dlp"),
                )

        threading.Thread(target=run, daemon=True).start()

    # ── ffmpeg path helpers ──────────────────────────────────────────────
    def _refresh_ffmpeg_status(self):
        self._update_dep_banner()
        path = self.ffmpeg_path
        if path and os.path.isfile(path):
            self.lbl_ffmpeg_status.config(text="Checking version...", fg=FG1)
            if hasattr(self, "btn_get_ffmpeg"):
                self.btn_get_ffmpeg.config(text="↑ Update ffmpeg")
            self._check_ffmpeg_version()
        elif path:
            self.lbl_ffmpeg_status.config(
                text="✗ Not found — verify the path above", fg=LOG_RED)
            if hasattr(self, "btn_get_ffmpeg"):
                self.btn_get_ffmpeg.config(text="↓ Get ffmpeg")
        else:
            self.lbl_ffmpeg_status.config(
                text="Not set — use Browse or ↓ Get ffmpeg (required for "
                     "merging formats)",
                fg=FG2)
            if hasattr(self, "btn_get_ffmpeg"):
                self.btn_get_ffmpeg.config(text="↓ Get ffmpeg")

    def _check_ffmpeg_version(self):
        path = self.ffmpeg_path

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_ffmpeg_status.config(
                    text=t, fg=c),
            )

        def run():
            try:
                r = subprocess.run(
                    [path, "-version"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_no_window_flags(),
                )
                if r.returncode != 0:
                    _status(
                        "⚠ ffmpeg failed to start — binary may be "
                        "corrupted. Click ↑ Update ffmpeg", LOG_RED,
                    )
                    return
                first_line = r.stdout.splitlines()[0] if r.stdout else ""
                if "version" in first_line:
                    ver = first_line.split("version")[-1].strip().split()[0]
                else:
                    ver = "?"
                _status(f"✓ ffmpeg {ver}", LOG_OK)
            except Exception as exc:
                _status(f"⚠ Could not run ffmpeg: {exc}", LOG_RED)

        threading.Thread(target=run, daemon=True).start()

    def _set_ffmpeg_path(self, path: str):
        self.ffmpeg_path = path
        self.txt_ffmpeg.delete(0, "end")
        self.txt_ffmpeg.insert(0, path)
        cfg = load_config()
        cfg["ffmpeg_path"] = path
        save_config(cfg)
        self._refresh_ffmpeg_status()

    def _on_ffmpeg_entry_change(self, _=None):
        self._set_ffmpeg_path(self.txt_ffmpeg.get().strip())

    def _browse_ffmpeg(self):
        path = filedialog.askopenfilename(
            title="Locate ffmpeg executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=(
                str(Path(self.ffmpeg_path).parent) if self.ffmpeg_path
                else str(Path.home())
            ),
        )
        if path:
            self._set_ffmpeg_path(path)

    def _autodetect_ffmpeg(self):
        found = find_ffmpeg()
        if found:
            self._set_ffmpeg_path(found)
        else:
            self.lbl_ffmpeg_status.config(
                text="Auto-detect failed — use Browse or ↓ Get ffmpeg to "
                     "download it", fg=LOG_RED)

    def _download_ffmpeg(self):
        dest_dir = BASE / "ffmpeg"
        action = (
            "Updating"
            if self.ffmpeg_path and os.path.isfile(self.ffmpeg_path)
            else "Downloading"
        )
        self.btn_get_ffmpeg.config(state="disabled", text=f"{action}...")

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_ffmpeg_status.config(
                    text=t, fg=c),
            )

        def reporthook(count, block_size, total_size):
            mb_done = count * block_size / 1_048_576
            if total_size > 0:
                pct = min(100, count * block_size * 100 // total_size)
                total_mb = total_size / 1_048_576
                msg = (
                    f"Downloading ffmpeg... {mb_done:.1f} / "
                    f"{total_mb:.1f} MB ({pct}%)"
                )
            else:
                msg = f"Downloading ffmpeg... {mb_done:.1f} MB"
            self.after(
                0,
                lambda m=msg: self.lbl_ffmpeg_status.config(
                    text=m, fg=BLUE),
            )

        def run():
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                ) as tmp:
                    tmp_path = tmp.name
                urllib.request.urlretrieve(
                    FFMPEG_RELEASE_URL, tmp_path, reporthook)
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
                self.after(
                    0,
                    lambda: self.btn_get_ffmpeg.config(
                        state="normal", text="↓ Get ffmpeg"),
                )

        threading.Thread(target=run, daemon=True).start()

    # ── Python / Spleeter path helpers ──────────────────────────────────
    def _refresh_spleeter_status(self):
        path = self.python_path
        if not path or not os.path.isfile(path):
            self.lbl_spleeter_status.config(
                text="No Python interpreter set — use Browse or "
                     "Auto-detect", fg=FG2)
            return
        self.lbl_spleeter_status.config(
            text="Checking audio tools installation...", fg=FG1)

        def run():
            spleeter_ok = check_spleeter_installed(path)
            librosa_ok = check_librosa_installed(path)
            if spleeter_ok and librosa_ok:
                self.after(
                    0,
                    lambda: self.lbl_spleeter_status.config(
                        text="✓ Spleeter + tempo/click tools are "
                             f"installed ({path})", fg=LOG_OK),
                )
            elif spleeter_ok:
                self.after(
                    0,
                    lambda: self.lbl_spleeter_status.config(
                        text="⚠ Spleeter installed, but librosa "
                             "(tempo/click) is missing — click ↓ Install "
                             "Spleeter",
                        fg=LOG_WARN),
                )
            elif librosa_ok:
                self.after(
                    0,
                    lambda: self.lbl_spleeter_status.config(
                        text="⚠ Tempo/click tools installed, but "
                             "Spleeter is missing — click ↓ Install "
                             "Spleeter",
                        fg=LOG_WARN),
                )
            else:
                self.after(
                    0,
                    lambda: self.lbl_spleeter_status.config(
                        text="✗ Not installed for this interpreter — "
                             "click ↓ Install Spleeter",
                        fg=LOG_WARN),
                )

        threading.Thread(target=run, daemon=True).start()

    def _set_python_path(self, path: str):
        self.python_path = path
        self.txt_python.delete(0, "end")
        self.txt_python.insert(0, path)
        cfg = load_config()
        cfg["python_path"] = path
        save_config(cfg)
        self._refresh_spleeter_status()

    def _on_python_entry_change(self, _=None):
        self._set_python_path(self.txt_python.get().strip())

    def _browse_python(self):
        path = filedialog.askopenfilename(
            title="Locate a Python interpreter",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=(
                str(Path(self.python_path).parent) if self.python_path
                else str(Path.home())
            ),
        )
        if path:
            self._set_python_path(path)

    def _autodetect_python(self):
        found = find_python()
        if found:
            self._set_python_path(found)
        else:
            self.lbl_spleeter_status.config(
                text="Auto-detect failed — install Python 3.10 and use "
                     "Browse", fg=LOG_RED)

    def _install_spleeter(self):
        path = self.python_path
        if not path or not os.path.isfile(path):
            messagebox.showwarning(
                "Python not set",
                "Set a Python interpreter path first (Browse or "
                "Auto-detect).")
            return

        self.btn_install_spleeter.config(state="disabled", text="Installing...")
        self.lbl_spleeter_status.config(
            text="Installing audio tools (this can take a few "
                 "minutes)...", fg=BLUE)
        self._log(
            "Installing Spleeter + librosa via pip — this can take "
            "several minutes...", "blue")

        def run():
            try:
                proc = subprocess.Popen(
                    # numpy<2 is pinned alongside spleeter — the pinned
                    # TensorFlow version spleeter depends on is compiled
                    # against numpy's 1.x ABI and crashes on import
                    # ("_ARRAY_API not found") under numpy 2.
                    # librosa/soundfile power tempo detection and
                    # click-track generation.
                    [path, "-m", "pip", "install", "spleeter", "numpy<2",
                     "librosa", "soundfile"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=_no_window_flags(),
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self._q.put((line, "gray"))
                proc.wait()
                spleeter_ok = check_spleeter_installed(path)
                librosa_ok = check_librosa_installed(path)
                if proc.returncode == 0 and spleeter_ok and librosa_ok:
                    self._q.put(
                        ("Spleeter + librosa installed successfully.",
                         "ok"))
                    self.after(
                        0,
                        lambda: self.lbl_spleeter_status.config(
                            text="✓ Spleeter + tempo/click tools "
                                 "installed", fg=LOG_OK),
                    )
                elif proc.returncode == 0:
                    missing = (
                        ("Spleeter" if not spleeter_ok else "")
                        + (" librosa" if not librosa_ok else "")
                    )
                    self._q.put((
                        f"Installed but failed to import: "
                        f"{missing.strip()} — see Output Log above.",
                        "fail",
                    ))
                    self.after(
                        0,
                        lambda m=missing: self.lbl_spleeter_status.config(
                            text=f"✗ Not importable: {m.strip()} — see "
                                 "Output Log", fg=LOG_RED),
                    )
                else:
                    self._q.put((
                        f"Installation failed — exit code "
                        f"{proc.returncode}.", "fail",
                    ))
                    self.after(
                        0,
                        lambda: self.lbl_spleeter_status.config(
                            text="✗ Installation failed — see Output "
                                 "Log", fg=LOG_RED),
                    )
            except Exception as exc:
                self._q.put((f"Error installing audio tools: {exc}", "err"))
                self.after(
                    0,
                    lambda e=str(exc): self.lbl_spleeter_status.config(
                        text=f"✗ Installation error: {e}", fg=LOG_RED),
                )
            finally:
                self.after(
                    0,
                    lambda: self.btn_install_spleeter.config(
                        state="normal", text="↓ Install Spleeter"),
                )

        threading.Thread(target=run, daemon=True).start()

    # ── Spleeter portable runtime (no system Python required) ──────────
    def _setup_embedded_python(self):
        self.btn_setup_spleeter.config(state="disabled", text="Setting up...")
        self.btn_install_spleeter.config(state="disabled")
        self.lbl_spleeter_status.config(
            text="Starting Spleeter auto-setup...", fg=BLUE)

        dest_dir = BASE / "python-embed"
        py_exe = dest_dir / "python.exe"

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_spleeter_status.config(
                    text=t, fg=c),
            )

        def reporthook(label):
            def hook(count, block_size, total_size):
                mb = count * block_size / 1_048_576
                if total_size > 0:
                    pct = min(100, count * block_size * 100 // total_size)
                    tmb = total_size / 1_048_576
                    _status(f"{label}... {mb:.1f}/{tmb:.1f} MB ({pct}%)",
                            BLUE)
                else:
                    _status(f"{label}... {mb:.1f} MB", BLUE)
            return hook

        def run_stream(cmd):
            """Run cmd, stream its output into the log, return the exit
            code."""
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=_no_window_flags(),
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._q.put((line, "gray"))
            proc.wait()
            return proc.returncode

        def run():
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)

                if not py_exe.is_file():
                    self._q.put((
                        "Downloading portable Python 3.10 runtime "
                        "(private to this app)...", "blue",
                    ))
                    with tempfile.NamedTemporaryFile(
                        suffix=".zip", delete=False
                    ) as tmp:
                        tmp_path = tmp.name
                    urllib.request.urlretrieve(
                        EMBED_PYTHON_URL, tmp_path,
                        reporthook("Downloading Python runtime"))
                    _status("Extracting Python runtime...", BLUE)
                    with zipfile.ZipFile(tmp_path, "r") as zf:
                        zf.extractall(dest_dir)
                    os.unlink(tmp_path)

                    # Embeddable Python ships with site-packages disabled
                    # by default — enable it so pip-installed packages
                    # import.
                    for pth in dest_dir.glob("python3*._pth"):
                        text = pth.read_text(encoding="utf-8")
                        pth.write_text(
                            text.replace("#import site", "import site"),
                            encoding="utf-8")

                # Bootstrap pip if it isn't already usable in this
                # runtime
                has_pip = subprocess.run(
                    [str(py_exe), "-m", "pip", "--version"],
                    capture_output=True, creationflags=_no_window_flags(),
                ).returncode == 0
                if not has_pip:
                    self._q.put(("Bootstrapping pip...", "blue"))
                    _status("Bootstrapping pip...", BLUE)
                    get_pip = dest_dir / "get-pip.py"
                    urllib.request.urlretrieve(GET_PIP_URL, str(get_pip))
                    ec = run_stream([
                        str(py_exe), str(get_pip),
                        "--no-warn-script-location",
                    ])
                    try:
                        get_pip.unlink()
                    except OSError:
                        pass
                    if ec != 0:
                        raise RuntimeError(
                            f"Failed to bootstrap pip (exit code {ec})")

                need_spleeter = not check_spleeter_installed(str(py_exe))
                need_librosa = not check_librosa_installed(str(py_exe))
                if not need_spleeter and not need_librosa:
                    self._q.put((
                        "Spleeter + librosa already installed in the "
                        "portable runtime.", "ok",
                    ))
                else:
                    pkgs = []
                    if need_spleeter:
                        # numpy<2 pinned alongside spleeter — the
                        # TensorFlow version it depends on is built
                        # against numpy's 1.x ABI and fails to import
                        # under numpy 2.x ("_ARRAY_API not found").
                        pkgs += ["spleeter", "numpy<2"]
                    if need_librosa:
                        pkgs += ["librosa", "soundfile"]
                    self._q.put((
                        f"Installing {', '.join(pkgs)} (downloads "
                        "TensorFlow — several minutes)...", "blue",
                    ))
                    _status(
                        "Installing audio tools — this can take "
                        "several minutes...", BLUE)
                    ec = run_stream(
                        [str(py_exe), "-m", "pip", "install"] + pkgs)
                    if ec != 0:
                        raise RuntimeError(
                            f"pip install failed (exit code {ec})")
                    if not check_spleeter_installed(str(py_exe)):
                        raise RuntimeError(
                            "Spleeter installed but failed to import — "
                            "check the Output Log above for the real "
                            "error")
                    if not check_librosa_installed(str(py_exe)):
                        raise RuntimeError(
                            "librosa installed but failed to import — "
                            "check the Output Log above for the real "
                            "error")
                    self._q.put((
                        "Spleeter + librosa installed successfully.",
                        "ok",
                    ))

                self.after(0, lambda: self._set_python_path(str(py_exe)))
                self._q.put((
                    "Audio tools are ready — no system Python required.",
                    "ok",
                ))
                _status(
                    "✓ Audio tools ready (portable runtime, no system "
                    "Python needed)", LOG_OK)
            except Exception as exc:
                self._q.put(
                    (f"Audio tools auto-setup failed: {exc}", "fail"))
                _status(f"✗ Auto-setup failed: {exc}", LOG_RED)
            finally:
                self.after(
                    0,
                    lambda: self.btn_setup_spleeter.config(
                        state="normal",
                        text="⚡  Auto-Setup Audio Tools  —  no Python "
                             "install needed"),
                )
                self.after(
                    0,
                    lambda: self.btn_install_spleeter.config(
                        state="normal"),
                )

        threading.Thread(target=run, daemon=True).start()

    # ── Quick Setup ────────────────────────────────────────────────────
    def _quick_setup(self):
        self.btn_quick_setup.config(state="disabled", text="Setting up...")
        self.btn_get_ytdlp.config(state="disabled")
        self.btn_get_ffmpeg.config(state="disabled")

        lock = threading.Lock()
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
            dest_dir = BASE / "yt-dlp"
            dest_file = dest_dir / "yt-dlp.exe"

            def rh(count, block_size, total_size):
                mb = count * block_size / 1_048_576
                if total_size > 0:
                    pct = min(100, count * block_size * 100 // total_size)
                    tmb = total_size / 1_048_576
                    msg = (
                        f"Downloading yt-dlp... {mb:.1f}/{tmb:.1f} MB "
                        f"({pct}%)"
                    )
                else:
                    msg = f"Downloading yt-dlp... {mb:.1f} MB"
                self.after(
                    0,
                    lambda m=msg: self.lbl_ytdlp_status.config(
                        text=m, fg=BLUE),
                )

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(
                    YTDLP_RELEASE_URL, str(dest_file), rh)
                self.after(0, lambda: self._set_ytdlp_path(str(dest_file)))
            except Exception as exc:
                self.after(
                    0,
                    lambda e=str(exc): self.lbl_ytdlp_status.config(
                        text=f"yt-dlp download failed: {e}", fg=LOG_RED),
                )
            finally:
                on_both_done()

        def dl_ffmpeg():
            dest_dir = BASE / "ffmpeg"

            def _st(text, color):
                self.after(
                    0,
                    lambda t=text, c=color: self.lbl_ffmpeg_status.config(
                        text=t, fg=c),
                )

            def rh(count, block_size, total_size):
                mb = count * block_size / 1_048_576
                if total_size > 0:
                    pct = min(100, count * block_size * 100 // total_size)
                    tmb = total_size / 1_048_576
                    msg = (
                        f"Downloading ffmpeg... {mb:.1f}/{tmb:.1f} MB "
                        f"({pct}%)"
                    )
                else:
                    msg = f"Downloading ffmpeg... {mb:.1f} MB"
                self.after(
                    0,
                    lambda m=msg: self.lbl_ffmpeg_status.config(
                        text=m, fg=BLUE),
                )

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                ) as tmp:
                    tmp_path = tmp.name
                urllib.request.urlretrieve(FFMPEG_RELEASE_URL, tmp_path, rh)
                _st("Extracting ffmpeg...", BLUE)
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    for member in zf.namelist():
                        fname = member.split("/")[-1]
                        if fname in ("ffmpeg.exe", "ffprobe.exe"):
                            (dest_dir / fname).write_bytes(
                                zf.read(member))
                os.unlink(tmp_path)
                ffmpeg_exe = str(dest_dir / "ffmpeg.exe")
                self.after(0, lambda: self._set_ffmpeg_path(ffmpeg_exe))
            except Exception as exc:
                _st(f"ffmpeg download failed: {exc}", LOG_RED)
            finally:
                on_both_done()

        threading.Thread(target=dl_ytdlp, daemon=True).start()
        threading.Thread(target=dl_ffmpeg, daemon=True).start()

    # ── App self-update ──────────────────────────────────────────────────
    def _check_app_update(self):
        self.btn_check_update.config(state="disabled", text="Checking...")
        self.lbl_update_status.config(text="Checking for updates...", fg=FG1)

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_update_status.config(
                    text=t, fg=c),
            )

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
                exe_asset = next(
                    (a for a in assets if a["name"] == "dlp-ui.exe"), None)

                if not exe_asset:
                    _status(
                        "No dlp-ui.exe asset found in latest release.",
                        LOG_WARN)
                    return

                if parse_version(latest_tag) <= parse_version(VERSION):
                    _status(f"✓ v{VERSION} — already up to date", LOG_OK)
                    return

                dl_url = exe_asset["browser_download_url"]
                _status(
                    f"Update available: v{VERSION} → v{latest_tag}  —  "
                    "click the button to install",
                    LOG_WARN,
                )
                self.after(
                    0,
                    lambda u=dl_url, v=latest_tag: self._offer_update(u, v),
                )
            except Exception as exc:
                _status(f"Could not check for updates: {exc}", LOG_RED)
            finally:
                self.after(
                    0,
                    lambda: self.btn_check_update.config(
                        state="normal", text="Check for Updates",
                        command=self._check_app_update),
                )

        threading.Thread(target=run, daemon=True).start()

    def _offer_update(self, download_url: str, new_ver: str):
        self.btn_check_update.config(
            state="normal",
            text=f"↓  Install v{new_ver}",
            command=lambda: self._download_and_apply_update(
                download_url, new_ver),
        )

    def _download_and_apply_update(self, download_url: str, new_ver: str):
        if not getattr(sys, "frozen", False):
            self.lbl_update_status.config(
                text="Self-update only works in the compiled EXE, not "
                     "from source.",
                fg=LOG_WARN)
            return

        self.btn_check_update.config(state="disabled", text="Downloading...")

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_update_status.config(
                    text=t, fg=c),
            )

        def reporthook(count, block_size, total_size):
            mb = count * block_size / 1_048_576
            if total_size > 0:
                pct = min(100, count * block_size * 100 // total_size)
                tmb = total_size / 1_048_576
                msg = f"Downloading v{new_ver}... {mb:.1f}/{tmb:.1f} MB ({pct}%)"
            else:
                msg = f"Downloading v{new_ver}... {mb:.1f} MB"
            self.after(
                0,
                lambda m=msg: self.lbl_update_status.config(
                    text=m, fg=BLUE),
            )

        def run():
            current = Path(sys.executable)
            new_file = current.with_name("dlp-ui-update.exe")
            bat_file = current.with_name("_dlp-ui-updater.bat")
            try:
                urllib.request.urlretrieve(
                    download_url, str(new_file), reporthook)

                bat_file.write_text(
                    "@echo off\r\n"
                    "ping -n 3 127.0.0.1 > nul\r\n"
                    f'move /y "{new_file}" "{current}"\r\n'
                    f'start "" "{current}"\r\n'
                    "del \"%~f0\"\r\n",
                    encoding="utf-8",
                )

                _status(
                    f"v{new_ver} downloaded — restarting app...", LOG_OK)
                self.after(800, lambda: self._apply_update(bat_file))
            except Exception as exc:
                _status(f"Update failed: {exc}", LOG_RED)
                self.after(
                    0,
                    lambda: self.btn_check_update.config(
                        state="normal", text="Check for Updates",
                        command=self._check_app_update),
                )

        threading.Thread(target=run, daemon=True).start()

    def _apply_update(self, bat_file: Path):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["cmd", "/c", str(bat_file)], creationflags=flags)
        self.on_close()


class _SettingsWidgetFactory:
    """Small helper-widget factories shared by every group in this tab,
    scoped to a single parent container (mirrors the local closures the
    original monolithic `_build_settings` used)."""

    def __init__(self, inner: tk.Frame):
        self._inner = inner

    def grp(self, title):
        f = tk.LabelFrame(
            self._inner, text=title, bg=BG0, fg=FG1, bd=1,
            relief="groove", font=("Segoe UI", 9))
        f.pack(fill="x", padx=10, pady=(6, 0))
        f.columnconfigure(1, weight=1)
        return f

    @staticmethod
    def sbtn(parent, text, cmd, fg=FG0, border=BG3):
        return tk.Button(
            parent, text=text, bg=BG2, fg=fg, relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI", 9), command=cmd,
            highlightthickness=1, highlightbackground=border,
            activebackground=BG3, activeforeground=FG0)

    @staticmethod
    def ent(parent, default=""):
        e = tk.Entry(
            parent, bg=BG2, fg=FG0, insertbackground=FG0,
            relief="solid", bd=1, font=("Segoe UI", 9))
        if default:
            e.insert(0, default)
        return e

    @staticmethod
    def cbo(parent, vals):
        c = ttk.Combobox(
            parent, values=vals, state="readonly", font=("Segoe UI", 9))
        c.current(0)
        return c

    @staticmethod
    def chk(parent, text):
        var = tk.BooleanVar()
        cb = tk.Checkbutton(
            parent, text=text, variable=var, bg=BG0, fg=FG1,
            selectcolor=BG2, activebackground=BG0, activeforeground=FG0,
            font=("Segoe UI", 10))
        return cb, var

    @staticmethod
    def spn(parent, lo, hi, default):
        s = tk.Spinbox(
            parent, from_=lo, to=hi, bg=BG2, fg=FG0,
            insertbackground=FG0, buttonbackground=BG3, relief="solid",
            bd=1, font=("Segoe UI", 9), width=5)
        s.delete(0, "end")
        s.insert(0, str(default))
        return s

    @staticmethod
    def slbl(parent):
        lbl = tk.Label(
            parent, text="", bg=BG0, fg=FG2, font=("Segoe UI", 9),
            anchor="w")
        lbl.bind(
            "<Configure>",
            lambda e, w=lbl: w.configure(wraplength=max(1, e.width - 4)))
        return lbl

    @staticmethod
    def lbl10(parent, text):
        return tk.Label(
            parent, text=text, bg=BG0, fg=FG1, font=("Segoe UI", 10))

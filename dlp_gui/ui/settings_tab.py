"""Settings tab: dependency management (yt-dlp/ffmpeg/Python + Spleeter
audio tools), download post-processing options, and app self-update.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import tkinter as tk
import urllib.request
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox

from .. import fonts, widgets
from ..constants import APP_RELEASES_API, VERSION
from ..dependencies import (
    EMBED_PYTHON_URL, EXE, FFMPEG_RELEASE_URL, GET_PIP_URL, IS_MACOS,
    IS_WINDOWS, YTDLP_RELEASE_URL, check_librosa_installed,
    check_spleeter_installed, find_ffmpeg, find_python, find_ytdlp,
)
from ..email_report import send_error_report
from ..paths import BASE, load_config, parse_version, save_config
from ..theme import (
    ACCENT, BG0, BG1, BG2, BG3, BLUE, FG0, FG1, FG2, LOG_OK, LOG_RED,
    LOG_WARN,
)

# macOS/Linux binaries have no extension, so an "*.exe" file-dialog
# filter would hide every real match — only apply it on Windows.
_EXE_FILETYPES = (
    [("Executable", "*.exe"), ("All files", "*.*")] if IS_WINDOWS
    else [("All files", "*")]
)


def _no_window_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def _update_asset_names():
    """GitHub release asset name(s) to look for when self-updating, in
    priority order — an arch-specific macOS build first, falling back
    to a universal one."""
    if IS_MACOS:
        arch = (
            "arm64" if platform.machine() in ("arm64", "aarch64")
            else "x86_64"
        )
        return [f"MD-Tools-macos-{arch}.zip", "MD-Tools-macos.zip"]
    return ["MD-Tools.exe"]


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
            troughcolor=BG1, activebackground=BG3)
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

        widgets.category_header(inner, "Setup")
        self._build_dependencies_group(inner)
        self._build_audio_tools_group(inner)

        widgets.category_header(inner, "Download behavior")
        self._build_post_processing_group(inner)
        self._build_subtitles_group(inner)
        self._build_playlist_group(inner)
        self._build_output_template_group(inner)

        widgets.category_header(inner, "Advanced & network")
        self._build_network_group(inner)
        self._build_extra_args_group(inner)

        widgets.category_header(inner, "Application")
        self._build_app_update_group(inner)
        self._build_error_reporting_group(inner)

        tk.Frame(inner, bg=BG0, height=12).pack()

    # ── Dependencies group ─────────────────────────────────────────────
    def _build_dependencies_group(self, parent):
        card = widgets.Card(
            parent, "Dependencies",
            "yt-dlp fetches video and audio; ffmpeg merges formats, "
            "converts audio, and embeds thumbnails. Most downloads "
            "need both.")
        g = card.body
        g.columnconfigure(0, weight=1)

        # ── yt-dlp ──────────────────────────────────────────────────
        tk.Label(
            g, text="yt-dlp", bg=BG2, fg=FG0, font=fonts.body_bold(10),
        ).grid(row=0, column=0, sticky="W", pady=(0, 4))
        self.txt_ytdlp = widgets.entry(g, self.ytdlp_path)
        self.txt_ytdlp.grid(row=1, column=0, sticky="EW", ipady=6)

        row1 = tk.Frame(g, bg=BG2)
        row1.grid(row=2, column=0, sticky="EW", pady=(6, 0))
        row1.columnconfigure(0, weight=1)
        self.lbl_ytdlp_status = widgets.status_label(row1)
        self.lbl_ytdlp_status.grid(row=0, column=0, sticky="EW")
        cluster1 = tk.Frame(row1, bg=BG2)
        cluster1.grid(row=0, column=1, sticky="E")
        widgets.secondary_button(
            cluster1, "Browse", self._browse_ytdlp,
        ).pack(side="left", ipady=4)
        widgets.secondary_button(
            cluster1, "Auto-detect", self._autodetect_ytdlp,
        ).pack(side="left", padx=(6, 0), ipady=4)
        self.btn_get_ytdlp = widgets.secondary_button(
            cluster1, "↓ Get yt-dlp", self._download_ytdlp)
        self.btn_get_ytdlp.pack(side="left", padx=(6, 0), ipady=4)
        self.ytdlp_activity = widgets.ActivityBar(row1, bg=BG2)
        self.ytdlp_activity.grid(
            row=1, column=0, columnspan=2, sticky="EW", pady=(6, 0))

        tk.Frame(g, bg=BG3, height=1).grid(
            row=3, column=0, sticky="EW", pady=14)

        # ── ffmpeg ──────────────────────────────────────────────────
        tk.Label(
            g, text="ffmpeg", bg=BG2, fg=FG0, font=fonts.body_bold(10),
        ).grid(row=4, column=0, sticky="W", pady=(0, 4))
        self.txt_ffmpeg = widgets.entry(g, self.ffmpeg_path)
        self.txt_ffmpeg.grid(row=5, column=0, sticky="EW", ipady=6)

        row2 = tk.Frame(g, bg=BG2)
        row2.grid(row=6, column=0, sticky="EW", pady=(6, 0))
        row2.columnconfigure(0, weight=1)
        self.lbl_ffmpeg_status = widgets.status_label(row2)
        self.lbl_ffmpeg_status.grid(row=0, column=0, sticky="EW")
        cluster2 = tk.Frame(row2, bg=BG2)
        cluster2.grid(row=0, column=1, sticky="E")
        widgets.secondary_button(
            cluster2, "Browse", self._browse_ffmpeg,
        ).pack(side="left", ipady=4)
        widgets.secondary_button(
            cluster2, "Auto-detect", self._autodetect_ffmpeg,
        ).pack(side="left", padx=(6, 0), ipady=4)
        self.btn_get_ffmpeg = widgets.secondary_button(
            cluster2, "↓ Get ffmpeg", self._download_ffmpeg)
        self.btn_get_ffmpeg.pack(side="left", padx=(6, 0), ipady=4)
        self.ffmpeg_activity = widgets.ActivityBar(row2, bg=BG2)
        self.ffmpeg_activity.grid(
            row=1, column=0, columnspan=2, sticky="EW", pady=(6, 0))

        self.btn_quick_setup = widgets.primary_button(
            g, "⚡  Quick Setup — download yt-dlp + ffmpeg",
            self._quick_setup)
        self.btn_quick_setup.grid(
            row=7, column=0, sticky="EW", pady=(16, 0), ipady=8)
        self.quick_setup_activity = widgets.ActivityBar(g, bg=BG2)
        self.quick_setup_activity.grid(
            row=8, column=0, sticky="EW", pady=(6, 0))

        self.txt_ytdlp.bind("<FocusOut>", self._on_ytdlp_entry_change)
        self.txt_ytdlp.bind("<Return>", self._on_ytdlp_entry_change)
        self.txt_ffmpeg.bind("<FocusOut>", self._on_ffmpeg_entry_change)
        self.txt_ffmpeg.bind("<Return>", self._on_ffmpeg_entry_change)
        self._refresh_ytdlp_status()
        self._refresh_ffmpeg_status()

    # ── Audio Tools group ──────────────────────────────────────────────
    def _build_audio_tools_group(self, parent):
        card = widgets.Card(
            parent, "Audio tools",
            "Split an MP3 into isolated stems (vocals, drums, bass...) "
            "with Deezer's Spleeter model, or detect tempo and "
            "generate a click track with librosa.")
        g = card.body
        g.columnconfigure(0, weight=1)

        self.btn_setup_spleeter = widgets.primary_button(
            g, "⚡  Auto-Setup Audio Tools — no Python install needed",
            self._setup_embedded_python)
        self.btn_setup_spleeter.grid(row=0, column=0, sticky="EW", ipady=8)
        self.spleeter_setup_activity = widgets.ActivityBar(g, bg=BG2)
        self.spleeter_setup_activity.grid(
            row=1, column=0, sticky="EW", pady=(6, 0))

        self.lbl_spleeter_status = widgets.status_label(g)
        self.lbl_spleeter_status.grid(
            row=2, column=0, sticky="EW", pady=(8, 0))

        # ── Quality & detection tuning ───────────────────────────────
        # Spleeter and librosa are fixed, pretrained/parameter-based
        # tools, not something this app retrains — but both expose
        # real levers for better output on a given track: Spleeter's
        # own post-separation filter, and librosa's tempo search range
        # + beat-tracking sensitivity.
        quality = tk.Frame(
            g, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        quality.grid(row=3, column=0, sticky="EW", pady=(14, 0))
        quality.columnconfigure(0, weight=1)

        tk.Label(
            quality, text="Separation & detection quality",
            bg=BG1, fg=FG1, font=fonts.small_bold(),
        ).grid(row=0, column=0, sticky="W", padx=12, pady=(10, 6))

        cb, self.v_mwf = widgets.checkbox(
            quality,
            "High-quality separation (MWF filter) — slower, cleaner "
            "stems", bg=BG1)
        cb.grid(row=1, column=0, sticky="W", padx=12, pady=(0, 10))

        trow = tk.Frame(quality, bg=BG1)
        trow.grid(row=2, column=0, sticky="EW", padx=12)
        widgets.field_label(
            trow, "Tempo search range (BPM) — corrects octave errors "
                  "(half/double the true tempo)", bg=BG1,
        ).pack(anchor="w")
        range_row = tk.Frame(trow, bg=BG1)
        range_row.pack(anchor="w", pady=(3, 0))
        self.spn_tempo_min = widgets.spinbox(range_row, 20, 300, 60, width=5)
        self.spn_tempo_min.pack(side="left", ipady=4)
        widgets.field_label(range_row, "to", bg=BG1).pack(
            side="left", padx=8)
        self.spn_tempo_max = widgets.spinbox(range_row, 20, 300, 200, width=5)
        self.spn_tempo_max.pack(side="left", ipady=4)

        srow = tk.Frame(quality, bg=BG1)
        srow.grid(row=3, column=0, sticky="EW", padx=12, pady=(10, 12))
        widgets.field_label(
            srow, "Beat tracking sensitivity — lower follows tempo "
                  "changes more loosely, higher holds a stricter grid",
            bg=BG1,
        ).grid(row=0, column=0, sticky="W")
        self.spn_sensitivity = widgets.spinbox(
            srow, 10, 400, 100, width=6)
        self.spn_sensitivity.grid(
            row=1, column=0, sticky="W", ipady=4, pady=(3, 0))

        adv = tk.Frame(
            g, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        adv.grid(row=4, column=0, sticky="EW", pady=(14, 0))
        adv.columnconfigure(0, weight=1)

        tk.Label(
            adv, text="Advanced: use an existing Python interpreter",
            bg=BG1, fg=FG1, font=fonts.small_bold(),
        ).grid(row=0, column=0, sticky="W", padx=12, pady=(10, 6))

        prow = tk.Frame(adv, bg=BG1)
        prow.grid(row=1, column=0, sticky="EW", padx=12)
        prow.columnconfigure(0, weight=1)
        self.txt_python = tk.Entry(
            prow, bg=BG2, fg=FG0, insertbackground=FG0, relief="flat",
            bd=0, highlightthickness=1, highlightbackground=BG3,
            highlightcolor=ACCENT, font=fonts.body())
        if self.python_path:
            self.txt_python.insert(0, self.python_path)
        self.txt_python.grid(row=0, column=0, sticky="EW", ipady=6)

        pbtns = tk.Frame(adv, bg=BG1)
        pbtns.grid(row=2, column=0, sticky="E", padx=12, pady=(8, 0))
        widgets.secondary_button(
            pbtns, "Browse", self._browse_python,
        ).pack(side="left", ipady=4)
        widgets.secondary_button(
            pbtns, "Auto-detect", self._autodetect_python,
        ).pack(side="left", padx=(6, 0), ipady=4)
        self.btn_install_spleeter = widgets.secondary_button(
            pbtns, "↓ Install Spleeter", self._install_spleeter)
        self.btn_install_spleeter.pack(side="left", padx=(6, 0), ipady=4)

        self.install_spleeter_activity = widgets.ActivityBar(adv, bg=BG1)
        self.install_spleeter_activity.grid(
            row=3, column=0, sticky="EW", padx=12, pady=(6, 0))

        tk.Label(
            adv, text=(
                "Must be Python 3.6–3.10 — newer versions can't build "
                "Spleeter's dependencies."
            ), bg=BG1, fg=FG2, font=fonts.small(), justify="left",
            wraplength=540,
        ).grid(row=4, column=0, sticky="W", padx=12, pady=(8, 10))

        self.txt_python.bind("<FocusOut>", self._on_python_entry_change)
        self.txt_python.bind("<Return>", self._on_python_entry_change)
        self._refresh_spleeter_status()

    # ── Post-Processing group ───────────────────────────────────────────
    def _build_post_processing_group(self, parent):
        card = widgets.Card(
            parent, "Post-processing", "Runs after each download finishes.")
        g = card.body
        g.columnconfigure(0, weight=1, uniform="pp")
        g.columnconfigure(1, weight=1, uniform="pp")

        left = tk.Frame(g, bg=BG2)
        left.grid(row=0, column=0, sticky="NW", padx=(0, 10))
        cb, self.v_thumb = widgets.checkbox(left, "Embed thumbnail as cover art")
        cb.pack(anchor="w", pady=(0, 6))
        cb, self.v_meta = widgets.checkbox(left, "Embed metadata (title, artist...)")
        cb.pack(anchor="w", pady=(0, 6))
        cb, self.v_chapters = widgets.checkbox(left, "Embed chapter markers")
        cb.pack(anchor="w")

        right = tk.Frame(g, bg=BG2)
        right.grid(row=0, column=1, sticky="NEW")
        right.columnconfigure(0, weight=1)
        cb, self.v_sponsor = widgets.checkbox(
            right, "Remove sponsored segments (SponsorBlock)")
        cb.grid(row=0, column=0, sticky="W", pady=(0, 10))

        widgets.field_label(right, "Remux to").grid(
            row=1, column=0, sticky="W", pady=(0, 3))
        self.cbo_remux = widgets.combobox(
            right, ["None", "mp4", "mkv", "mov", "webm", "avi", "flv"])
        self.cbo_remux.grid(row=2, column=0, sticky="EW", ipady=3)

        widgets.field_label(right, "Re-encode to").grid(
            row=3, column=0, sticky="W", pady=(10, 3))
        self.cbo_recode = widgets.combobox(
            right, ["None", "mp4", "mkv", "mov", "webm", "mp3", "m4a", "wav"])
        self.cbo_recode.grid(row=4, column=0, sticky="EW", ipady=3)

    # ── Subtitles group ──────────────────────────────────────────────────
    def _build_subtitles_group(self, parent):
        card = widgets.Card(
            parent, "Subtitles", "Grabs subtitle tracks alongside the video.")
        g = card.body
        g.columnconfigure(0, weight=1, uniform="sub")
        g.columnconfigure(1, weight=1, uniform="sub")

        left = tk.Frame(g, bg=BG2)
        left.grid(row=0, column=0, sticky="NW", padx=(0, 10))
        cb, self.v_subs = widgets.checkbox(left, "Download subtitles")
        cb.pack(anchor="w", pady=(0, 6))
        cb, self.v_auto_subs = widgets.checkbox(
            left, "Include auto-generated subtitles")
        cb.pack(anchor="w")

        right = tk.Frame(g, bg=BG2)
        right.grid(row=0, column=1, sticky="NEW")
        right.columnconfigure(0, weight=1)
        widgets.field_label(right, "Languages (comma-separated, e.g. en,ja)").grid(
            row=0, column=0, sticky="W", pady=(0, 3))
        self.txt_sub_langs = widgets.entry(right, "en")
        self.txt_sub_langs.grid(row=1, column=0, sticky="EW", ipady=6)

    # ── Playlist group ───────────────────────────────────────────────────
    def _build_playlist_group(self, parent):
        card = widgets.Card(
            parent, "Playlist handling",
            "What happens when a link points at more than one video.")
        g = card.body
        g.columnconfigure(0, weight=1)

        self.v_playlist = tk.StringVar(value="single")
        pl = tk.Frame(g, bg=BG2)
        pl.grid(row=0, column=0, sticky="W")
        for text, val in [
            ("Auto (let yt-dlp decide)", "auto"),
            ("Single video only", "single"),
            ("Always full playlist", "full"),
        ]:
            tk.Radiobutton(
                pl, text=text, variable=self.v_playlist, value=val,
                bg=BG2, fg=FG1, selectcolor=BG1,
                activebackground=BG2, activeforeground=FG0,
                font=fonts.body(),
            ).pack(side="left", padx=(0, 16))

    # ── Output template group ───────────────────────────────────────────
    def _build_output_template_group(self, parent):
        card = widgets.Card(
            parent, "Output filename", "How downloaded files get named.")
        g = card.body
        g.columnconfigure(0, weight=1)

        widgets.field_label(g, "Template (%(title)s.%(ext)s = default)").grid(
            row=0, column=0, sticky="W", pady=(0, 3))
        self.txt_tmpl = widgets.entry(g, "%(title)s.%(ext)s")
        self.txt_tmpl.grid(row=1, column=0, sticky="EW", ipady=6)

    # ── Network group ────────────────────────────────────────────────────
    def _build_network_group(self, parent):
        card = widgets.Card(
            parent, "Network",
            "Rate limits, retries, proxying, and browser cookies for "
            "gated content.")
        g = card.body
        g.columnconfigure(0, weight=1)

        top = tk.Frame(g, bg=BG2)
        top.grid(row=0, column=0, sticky="EW")
        top.columnconfigure(0, weight=2, uniform="net")
        top.columnconfigure(1, weight=1, uniform="net")
        top.columnconfigure(2, weight=2, uniform="net")
        top.columnconfigure(3, weight=1, uniform="net")

        widgets.field_label(top, "Rate limit (e.g. 5M, 500K)").grid(
            row=0, column=0, sticky="W")
        self.txt_rate = widgets.entry(top)
        self.txt_rate.grid(row=1, column=0, sticky="EW", ipady=6, padx=(0, 10))

        widgets.field_label(top, "Concurrent frags").grid(
            row=0, column=1, sticky="W")
        self.spn_frags = widgets.spinbox(top, 1, 32, 1)
        self.spn_frags.grid(row=1, column=1, sticky="W", ipady=4, padx=(0, 10))

        widgets.field_label(top, "Cookies from browser").grid(
            row=0, column=2, sticky="W")
        self.cbo_cookies = widgets.combobox(top, [
            "None", "chrome", "firefox", "edge", "brave", "opera",
            "safari", "vivaldi", "chromium",
        ])
        self.cbo_cookies.grid(row=1, column=2, sticky="EW", ipady=3, padx=(0, 10))

        widgets.field_label(top, "Retries").grid(row=0, column=3, sticky="W")
        self.spn_retries = widgets.spinbox(top, 1, 50, 10)
        self.spn_retries.grid(row=1, column=3, sticky="W", ipady=4)

        widgets.field_label(g, "Proxy (e.g. socks5://127.0.0.1:1080)").grid(
            row=1, column=0, sticky="W", pady=(14, 3))
        self.txt_proxy = widgets.entry(g)
        self.txt_proxy.grid(row=2, column=0, sticky="EW", ipady=6)

    # ── Extra args group ─────────────────────────────────────────────────
    def _build_extra_args_group(self, parent):
        card = widgets.Card(
            parent, "Extra yt-dlp arguments",
            "Power-user escape hatch — flags appended to every run "
            "verbatim.")
        g = card.body
        g.columnconfigure(0, weight=1)

        self.txt_extra = widgets.entry(g)
        self.txt_extra.grid(row=0, column=0, sticky="EW", ipady=6)

    # ── App Update group ─────────────────────────────────────────────────
    def _build_app_update_group(self, parent):
        card = widgets.Card(
            parent, "App update",
            "Checks GitHub for a newer build of DLP-UI itself.")
        g = card.body
        g.columnconfigure(0, weight=1)

        top_row = tk.Frame(g, bg=BG2)
        top_row.grid(row=0, column=0, sticky="EW")
        top_row.columnconfigure(0, weight=1)

        tk.Label(
            top_row, text=f"Current version: v{VERSION}", bg=BG2, fg=FG1,
            font=fonts.body(),
        ).grid(row=0, column=0, sticky="W")
        self.btn_check_update = widgets.secondary_button(
            top_row, "Check for Updates", self._check_app_update)
        self.btn_check_update.grid(row=0, column=1, ipady=4)

        self.update_activity = widgets.ActivityBar(g, bg=BG2)
        self.update_activity.grid(row=1, column=0, sticky="EW", pady=(6, 0))

        self.lbl_update_status = widgets.status_label(g)
        self.lbl_update_status.grid(row=2, column=0, sticky="EW", pady=(8, 0))

    # ── Error reporting group ──────────────────────────────────────────
    def _build_error_reporting_group(self, parent):
        card = widgets.Card(
            parent, "Error reporting",
            "Lets you email a failed download's log straight to the "
            "developer from the Download tab, via your own SMTP "
            "account. Credentials are stored only in your local "
            "dlp-ui-config.json, never bundled with the app.")
        g = card.body
        g.columnconfigure(0, weight=1)

        cfg = load_config()

        hrow = tk.Frame(g, bg=BG2)
        hrow.grid(row=0, column=0, sticky="EW")
        hrow.columnconfigure(0, weight=1)
        widgets.field_label(hrow, "SMTP server").grid(
            row=0, column=0, sticky="W")
        widgets.field_label(hrow, "Port").grid(
            row=0, column=1, padx=(10, 0), sticky="W")
        self.txt_smtp_host = widgets.entry(
            hrow, cfg.get("smtp_host", ""))
        self.txt_smtp_host.grid(row=1, column=0, sticky="EW", ipady=6)
        self.txt_smtp_port = widgets.entry(
            hrow, str(cfg.get("smtp_port", "587")))
        self.txt_smtp_port.configure(width=6)
        self.txt_smtp_port.grid(
            row=1, column=1, padx=(10, 0), ipady=6, sticky="W")

        widgets.field_label(g, "SMTP username (sender address)").grid(
            row=1, column=0, sticky="W", pady=(10, 3))
        self.txt_smtp_user = widgets.entry(g, cfg.get("smtp_user", ""))
        self.txt_smtp_user.grid(row=2, column=0, sticky="EW", ipady=6)

        widgets.field_label(
            g, "SMTP password (an app password, not your login "
               "password)",
        ).grid(row=3, column=0, sticky="W", pady=(10, 3))
        self.txt_smtp_password = widgets.entry(
            g, cfg.get("smtp_password", ""), show="*")
        self.txt_smtp_password.grid(row=4, column=0, sticky="EW", ipady=6)

        widgets.field_label(g, "Developer email (recipient)").grid(
            row=5, column=0, sticky="W", pady=(10, 3))
        self.txt_developer_email = widgets.entry(
            g, cfg.get("developer_email", ""))
        self.txt_developer_email.grid(row=6, column=0, sticky="EW", ipady=6)

        for entry in (
            self.txt_smtp_host, self.txt_smtp_port, self.txt_smtp_user,
            self.txt_smtp_password, self.txt_developer_email,
        ):
            entry.bind("<FocusOut>", self._save_smtp_settings)
            entry.bind("<Return>", self._save_smtp_settings)

        self.btn_test_smtp = widgets.secondary_button(
            g, "Send test email", self._send_test_email)
        self.btn_test_smtp.grid(
            row=7, column=0, sticky="EW", ipady=4, pady=(12, 0))
        self.smtp_test_activity = widgets.ActivityBar(g, bg=BG2)
        self.smtp_test_activity.grid(row=8, column=0, sticky="EW", pady=(6, 0))
        self.lbl_smtp_status = widgets.status_label(g)
        self.lbl_smtp_status.grid(row=9, column=0, sticky="EW", pady=(8, 0))

    def _save_smtp_settings(self, _=None):
        cfg = load_config()
        cfg["smtp_host"] = self.txt_smtp_host.get().strip()
        cfg["smtp_user"] = self.txt_smtp_user.get().strip()
        cfg["smtp_password"] = self.txt_smtp_password.get()
        cfg["developer_email"] = self.txt_developer_email.get().strip()
        try:
            cfg["smtp_port"] = int(self.txt_smtp_port.get().strip() or 587)
        except ValueError:
            cfg["smtp_port"] = 587
        save_config(cfg)

    def _send_test_email(self):
        self._save_smtp_settings()
        self.btn_test_smtp.config(state="disabled", text="Sending...")
        widgets.start_pulse(self.btn_test_smtp, weight="secondary")
        self.smtp_test_activity.start()

        def run():
            try:
                send_error_report(
                    {"url": "(test email)"},
                    "This is a test email from DLP-UI's Settings → "
                    "Error reporting — if you got this, sending error "
                    "reports from the Download tab will work too.",
                )
                self.after(
                    0,
                    lambda: self.lbl_smtp_status.config(
                        text="✓ Test email sent — check the inbox.",
                        fg=LOG_OK),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda e=str(exc): self.lbl_smtp_status.config(
                        text=f"✗ Failed to send: {e}", fg=LOG_RED),
                )
            finally:
                self.after(0, self.smtp_test_activity.stop)
                self.after(
                    0, lambda: widgets.stop_pulse(self.btn_test_smtp, BG2))
                self.after(
                    0,
                    lambda: self.btn_test_smtp.config(
                        state="normal", text="Send test email"),
                )

        threading.Thread(target=run, daemon=True).start()

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
            filetypes=_EXE_FILETYPES,
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
        dest_file = dest_dir / f"yt-dlp{EXE}"
        action = (
            "Updating"
            if self.ytdlp_path and os.path.isfile(self.ytdlp_path)
            else "Downloading"
        )
        self.btn_get_ytdlp.config(state="disabled", text=f"{action}...")
        widgets.start_pulse(self.btn_get_ytdlp, weight="secondary")
        self.ytdlp_activity.start()

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
                if not IS_WINDOWS:
                    dest_file.chmod(dest_file.stat().st_mode | 0o111)
                self.after(0, lambda: self._set_ytdlp_path(str(dest_file)))
            except Exception as exc:
                self.after(
                    0,
                    lambda e=str(exc): self.lbl_ytdlp_status.config(
                        text=f"Download failed: {e}", fg=LOG_RED),
                )
            finally:
                self.after(0, self.ytdlp_activity.stop)
                self.after(
                    0,
                    lambda: widgets.stop_pulse(self.btn_get_ytdlp, BG2),
                )
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
            filetypes=_EXE_FILETYPES,
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

    def _install_ffmpeg_via_brew(self, status_cb):
        """Install/update ffmpeg through Homebrew — the standard,
        trusted way to get a working ffmpeg on macOS (a copied
        Homebrew binary depends on Homebrew's shared libraries, so it
        can't simply be bundled into the app the way Windows bundles
        a static ffmpeg.exe).

        Returns the resolved ffmpeg path on success, None on failure;
        either way `status_cb(text, color)` is called with a
        human-readable result.
        """
        brew = shutil.which("brew")
        if not brew:
            status_cb(
                "Homebrew not found — install it from brew.sh, then "
                "run 'brew install ffmpeg', or use Browse to point at "
                "an existing ffmpeg.", LOG_RED,
            )
            return None
        self._q.put((
            "Installing ffmpeg via Homebrew (brew install ffmpeg)...",
            "blue",
        ))
        status_cb("Installing ffmpeg via Homebrew...", BLUE)
        try:
            proc = subprocess.Popen(
                [brew, "install", "ffmpeg"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._q.put((line, "gray"))
            proc.wait()
            if proc.returncode != 0:
                status_cb(
                    f"brew install failed — exit code {proc.returncode}. "
                    "See Output Log.", LOG_RED,
                )
                return None
        except Exception as exc:
            status_cb(f"ffmpeg install failed: {exc}", LOG_RED)
            return None
        found = find_ffmpeg()
        if not found:
            status_cb(
                "ffmpeg installed but could not be located — try "
                "Auto-detect.", LOG_WARN,
            )
        return found

    def _download_ffmpeg(self):
        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_ffmpeg_status.config(
                    text=t, fg=c),
            )

        if IS_MACOS:
            action = (
                "Updating"
                if self.ffmpeg_path and os.path.isfile(self.ffmpeg_path)
                else "Installing"
            )
            self.btn_get_ffmpeg.config(state="disabled", text=f"{action}...")
            widgets.start_pulse(self.btn_get_ffmpeg, weight="secondary")
            self.ffmpeg_activity.start()

            def run():
                found = self._install_ffmpeg_via_brew(_status)
                if found:
                    self.after(0, lambda f=found: self._set_ffmpeg_path(f))
                self.after(0, self.ffmpeg_activity.stop)
                self.after(
                    0, lambda: widgets.stop_pulse(self.btn_get_ffmpeg, BG2))
                self.after(
                    0,
                    lambda: self.btn_get_ffmpeg.config(
                        state="normal", text="↓ Get ffmpeg"),
                )

            threading.Thread(target=run, daemon=True).start()
            return

        dest_dir = BASE / "ffmpeg"
        action = (
            "Updating"
            if self.ffmpeg_path and os.path.isfile(self.ffmpeg_path)
            else "Downloading"
        )
        self.btn_get_ffmpeg.config(state="disabled", text=f"{action}...")
        widgets.start_pulse(self.btn_get_ffmpeg, weight="secondary")
        self.ffmpeg_activity.start()

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
                self.after(0, self.ffmpeg_activity.stop)
                self.after(
                    0, lambda: widgets.stop_pulse(self.btn_get_ffmpeg, BG2))
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
            filetypes=_EXE_FILETYPES,
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
        widgets.start_pulse(self.btn_install_spleeter, weight="secondary")
        self.install_spleeter_activity.start()
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
                self.after(0, self.install_spleeter_activity.stop)
                self.after(
                    0,
                    lambda: widgets.stop_pulse(
                        self.btn_install_spleeter, BG2),
                )
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
        widgets.start_pulse(self.btn_setup_spleeter, weight="primary")
        self.spleeter_setup_activity.start()
        self.lbl_spleeter_status.config(
            text="Starting Spleeter auto-setup...", fg=BLUE)

        dest_dir = BASE / "python-embed"
        py_exe = (
            dest_dir / "bin" / "python3" if IS_MACOS
            else dest_dir / "python.exe"
        )

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
                    suffix = ".tar.gz" if IS_MACOS else ".zip"
                    with tempfile.NamedTemporaryFile(
                        suffix=suffix, delete=False
                    ) as tmp:
                        tmp_path = tmp.name
                    urllib.request.urlretrieve(
                        EMBED_PYTHON_URL, tmp_path,
                        reporthook("Downloading Python runtime"))
                    _status("Extracting Python runtime...", BLUE)
                    if IS_MACOS:
                        # python-build-standalone archives wrap
                        # everything in a top-level "python/" dir —
                        # strip it so dest_dir/bin/python3 exists
                        # directly.
                        with tarfile.open(tmp_path, "r:gz") as tf:
                            for member in tf.getmembers():
                                parts = member.name.split("/", 1)
                                if len(parts) != 2 or not parts[1]:
                                    continue
                                member.name = parts[1]
                                tf.extract(member, dest_dir)
                        py_exe.chmod(py_exe.stat().st_mode | 0o111)
                    else:
                        with zipfile.ZipFile(tmp_path, "r") as zf:
                            zf.extractall(dest_dir)
                        # Embeddable Python ships with site-packages
                        # disabled by default — enable it so
                        # pip-installed packages import.
                        for pth in dest_dir.glob("python3*._pth"):
                            text = pth.read_text(encoding="utf-8")
                            pth.write_text(
                                text.replace(
                                    "#import site", "import site"),
                                encoding="utf-8")
                    os.unlink(tmp_path)

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
                self.after(0, self.spleeter_setup_activity.stop)
                self.after(
                    0,
                    lambda: widgets.stop_pulse(
                        self.btn_setup_spleeter, ACCENT),
                )
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
        widgets.start_pulse(self.btn_quick_setup, weight="primary")
        self.quick_setup_activity.start()
        self.ytdlp_activity.start()
        self.ffmpeg_activity.start()

        lock = threading.Lock()
        done = [0]

        def on_both_done():
            with lock:
                done[0] += 1
                if done[0] < 2:
                    return

            def re_enable():
                self.quick_setup_activity.stop()
                self.ytdlp_activity.stop()
                self.ffmpeg_activity.stop()
                widgets.stop_pulse(self.btn_quick_setup, ACCENT)
                self.btn_quick_setup.config(
                    state="normal",
                    text="⚡  Quick Setup  —  download yt-dlp + ffmpeg")
                self.btn_get_ytdlp.config(state="normal")
                self.btn_get_ffmpeg.config(state="normal")
            self.after(0, re_enable)

        def dl_ytdlp():
            dest_dir = BASE / "yt-dlp"
            dest_file = dest_dir / f"yt-dlp{EXE}"

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
                if not IS_WINDOWS:
                    dest_file.chmod(dest_file.stat().st_mode | 0o111)
                self.after(0, lambda: self._set_ytdlp_path(str(dest_file)))
            except Exception as exc:
                self.after(
                    0,
                    lambda e=str(exc): self.lbl_ytdlp_status.config(
                        text=f"yt-dlp download failed: {e}", fg=LOG_RED),
                )
            finally:
                self.after(0, self.ytdlp_activity.stop)
                on_both_done()

        def dl_ffmpeg():
            def _st(text, color):
                self.after(
                    0,
                    lambda t=text, c=color: self.lbl_ffmpeg_status.config(
                        text=t, fg=c),
                )

            if IS_MACOS:
                try:
                    found = self._install_ffmpeg_via_brew(_st)
                    if found:
                        self.after(
                            0, lambda f=found: self._set_ffmpeg_path(f))
                finally:
                    self.after(0, self.ffmpeg_activity.stop)
                    on_both_done()
                return

            dest_dir = BASE / "ffmpeg"

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
                self.after(0, self.ffmpeg_activity.stop)
                on_both_done()

        threading.Thread(target=dl_ytdlp, daemon=True).start()
        threading.Thread(target=dl_ffmpeg, daemon=True).start()

    # ── App self-update ──────────────────────────────────────────────────
    def _check_app_update(self):
        self.btn_check_update.config(state="disabled", text="Checking...")
        widgets.start_pulse(self.btn_check_update, weight="secondary")
        self.update_activity.start()
        self.lbl_update_status.config(text="Checking for updates...", fg=FG1)

        def _status(text, color):
            self.after(
                0,
                lambda t=text, c=color: self.lbl_update_status.config(
                    text=t, fg=c),
            )

        def run():
            offered = False
            try:
                req = urllib.request.Request(
                    APP_RELEASES_API,
                    headers={"User-Agent": f"dlp-ui/{VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())

                latest_tag = data.get("tag_name", "").lstrip("v")
                assets = data.get("assets", [])
                names = _update_asset_names()
                asset = next(
                    (a for a in assets if a["name"] in names), None)

                if not asset:
                    _status(
                        f"No {'/'.join(names)} asset found in latest "
                        "release.", LOG_WARN)
                    return

                if parse_version(latest_tag) <= parse_version(VERSION):
                    _status(f"✓ v{VERSION} — already up to date", LOG_OK)
                    return

                dl_url = asset["browser_download_url"]
                _status(
                    f"Update available: v{VERSION} → v{latest_tag}  —  "
                    "click the button to install",
                    LOG_WARN,
                )
                offered = True
                self.after(
                    0,
                    lambda u=dl_url, v=latest_tag: self._offer_update(u, v),
                )
            except Exception as exc:
                _status(f"Could not check for updates: {exc}", LOG_RED)
            finally:
                self.after(0, self.update_activity.stop)
                self.after(
                    0, lambda: widgets.stop_pulse(self.btn_check_update, BG2))
                # _offer_update already left the button in its "install
                # this update" state — don't stomp back over it.
                if not offered:
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
                text="Self-update only works in the packaged build, not "
                     "from source.",
                fg=LOG_WARN)
            return

        self.btn_check_update.config(state="disabled", text="Downloading...")
        widgets.start_pulse(self.btn_check_update, weight="secondary")
        self.update_activity.start()

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

        def _fail(msg):
            _status(msg, LOG_RED)
            self.after(0, self.update_activity.stop)
            self.after(
                0, lambda: widgets.stop_pulse(self.btn_check_update, BG2))
            self.after(
                0,
                lambda: self.btn_check_update.config(
                    state="normal", text="Check for Updates",
                    command=self._check_app_update),
            )

        def run_macos():
            # sys.executable is .../dlp-ui.app/Contents/MacOS/dlp-ui —
            # walk up to the .app bundle itself.
            app_root = Path(sys.executable).resolve().parent.parent.parent
            if app_root.suffix != ".app":
                _fail(
                    "Self-update only works from within the installed "
                    ".app bundle.")
                return
            tmp_zip = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                ) as tmp:
                    tmp_zip = tmp.name
                urllib.request.urlretrieve(download_url, tmp_zip, reporthook)

                _status("Extracting update...", BLUE)
                extract_dir = Path(tempfile.mkdtemp(prefix="dlp-ui-update-"))
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    zf.extractall(extract_dir)
                new_app = next(extract_dir.glob("*.app"), None)
                if not new_app:
                    raise RuntimeError(
                        "Update archive did not contain a .app bundle")

                # The app is still running out of app_root, so the
                # swap happens from a tiny detached shell script after
                # this process exits — same trick as the Windows .bat
                # updater below.
                sh_file = app_root.parent / "._dlp-ui-updater.sh"
                sh_file.write_text(
                    "#!/bin/sh\n"
                    "sleep 2\n"
                    f'rm -rf "{app_root}"\n'
                    f'mv "{new_app}" "{app_root}"\n'
                    f'open "{app_root}"\n'
                    'rm -- "$0"\n',
                    encoding="utf-8",
                )
                sh_file.chmod(sh_file.stat().st_mode | 0o111)

                _status(
                    f"v{new_ver} downloaded — restarting app...", LOG_OK)
                self.after(800, lambda: self._apply_update_macos(sh_file))
            except Exception as exc:
                _fail(f"Update failed: {exc}")
            finally:
                if tmp_zip and os.path.exists(tmp_zip):
                    os.unlink(tmp_zip)

        def run_windows():
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
                _fail(f"Update failed: {exc}")

        threading.Thread(
            target=run_macos if IS_MACOS else run_windows, daemon=True,
        ).start()

    def _apply_update(self, bat_file: Path):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["cmd", "/c", str(bat_file)], creationflags=flags)
        self.on_close()

    def _apply_update_macos(self, sh_file: Path):
        subprocess.Popen(["/bin/sh", str(sh_file)], start_new_session=True)
        self.on_close()

"""Download tab: URL entry, format/quality pickers, audio tools
checkboxes, the Download button, and the output log.
"""
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .. import fonts, widgets
from ..constants import (
    AUDIO_QUALITIES, FORMAT_TYPES, STEM_OPTIONS, TEMPO_MULTIPLIERS,
    TIME_SIGNATURE_OVERRIDES, VIDEO_QUALITIES,
)
from ..dependencies import check_librosa_installed, check_spleeter_installed
from ..email_report import send_error_report, smtp_config_ready
from ..theme import (
    ACCENT, ACCENT_HOVER, ACCENT_INK, BG0, BG1, BG2, BG3, BLUE, FG0, FG1,
    FG2, LOG_FAIL, LOG_GRAY, LOG_GREEN, LOG_OK, LOG_RED, LOG_WARN,
)
from ..widgets import PlaceholderEntry
from ..ytdlp_args import build_args

_STALE_HINTS = [
    "nsig extraction failed",
    "Precondition check failed",
    "Only images are available",
]

_PLAYLIST_URL_RE = re.compile(r"[?&]list=([^&]+)", re.IGNORECASE)

# Marker prefix asked of yt-dlp (via --print) to report the final,
# post-processed file path unambiguously — far more reliable than
# scraping the wording of whichever postprocessor log line happens to
# fire (it varies: "[ExtractAudio] Destination:", "Not converting
# audio...", "[Merger] Merging formats into...", etc).
_SPLIT_TARGET_PREFIX = "SPLIT_TARGET:"


def _is_playlist_url(url):
    """Best-effort check for whether a pasted link points at a YouTube
    playlist (or a video that's part of one) rather than a single
    video."""
    if not url:
        return False
    if "/playlist" in url.lower():
        return True
    return bool(_PLAYLIST_URL_RE.search(url))


class DownloadTabMixin:
    """Adds the Download tab and its behavior to the main App window."""

    # ── UI construction ───────────────────────────────────────────────
    # The log always keeps at least this much height, however tall
    # the audio tools panel above gets — it's what you watch while a
    # download runs, so it must never be the part that silently loses
    # the fight for space. (The other half of that guarantee is the
    # capped-growth audio tools body — see _AUDIO_BODY_CAP.)
    _LOG_MIN_HEIGHT = 150

    def _build_download(self):
        p = self.tab_dl
        p.columnconfigure(0, weight=1)
        p.rowconfigure(9, weight=1, minsize=self._LOG_MIN_HEIGHT)

        # URL — the one thing this whole app is for, so it's the
        # largest, most prominent field on the page.
        tk.Label(
            p, text="Video URL", bg=BG0, fg=FG1, font=fonts.body(11),
        ).grid(row=0, column=0, padx=18, pady=(12, 3), sticky="W")
        url_wrap = tk.Frame(p, bg=BG0)
        url_wrap.grid(row=1, column=0, padx=18, sticky="EW")
        url_wrap.columnconfigure(0, weight=1)

        self.txt_url = PlaceholderEntry(
            url_wrap, placeholder="Paste a link here...",
            bg=BG2, fg=FG0, insertbackground=FG0,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=BG3, highlightcolor=ACCENT,
            font=fonts.body(12))
        self.txt_url.grid(row=0, column=0, sticky="EW", ipady=8)
        self.txt_url.bind("<KeyRelease>", self._check_playlist_url)
        self.txt_url.bind(
            "<<Paste>>", lambda e: self.after(10, self._check_playlist_url))

        self.lbl_playlist_warn = tk.Label(
            url_wrap, text="", bg=BG0, fg=ACCENT, font=fonts.small(),
            justify="left", anchor="w")
        self.lbl_playlist_warn.bind(
            "<Configure>",
            lambda e: self.lbl_playlist_warn.configure(
                wraplength=max(1, e.width - 4)),
        )

        # Format / Quality
        fq = tk.Frame(p, bg=BG0)
        fq.grid(row=2, column=0, padx=18, pady=(8, 0), sticky="EW")
        fq.columnconfigure(0, weight=1)
        fq.columnconfigure(1, weight=1)
        widgets.field_label(fq, "Format", bg=BG0).grid(
            row=0, column=0, sticky="W")
        widgets.field_label(fq, "Quality / resolution", bg=BG0).grid(
            row=0, column=1, padx=(10, 0), sticky="W")
        self.cbo_fmt = widgets.combobox(fq, list(FORMAT_TYPES))
        self.cbo_fmt.grid(row=1, column=0, sticky="EW", ipady=3, pady=(3, 0))
        self.cbo_qual = widgets.combobox(fq, list(VIDEO_QUALITIES))
        self.cbo_qual.grid(
            row=1, column=1, sticky="EW", padx=(10, 0), ipady=3, pady=(3, 0))
        self.cbo_fmt.bind("<<ComboboxSelected>>", self._fmt_changed)

        self._build_audio_tools_frame(p)

        # Destination
        widgets.field_label(p, "Destination folder", bg=BG0).grid(
            row=4, column=0, padx=18, pady=(8, 2), sticky="W")
        dest = tk.Frame(p, bg=BG0)
        dest.grid(row=5, column=0, padx=18, sticky="EW")
        dest.columnconfigure(0, weight=1)
        self.txt_dest = widgets.entry(dest)
        self.txt_dest.insert(0, str(Path.home() / "Videos"))
        self.txt_dest.grid(row=0, column=0, sticky="EW", ipady=6)
        widgets.secondary_button(dest, "Browse…", self._browse).grid(
            row=0, column=1, padx=(8, 0), ipady=6)

        # Dependency reminder — warns before downloading if yt-dlp/ffmpeg
        # aren't ready. A bordered banner (not just colored text) so it
        # reads as a real alert, not a stray line of text.
        self.dep_banner = tk.Frame(
            p, bg=BG2, cursor="hand2", highlightthickness=1)
        self.lbl_dep_banner = tk.Label(
            self.dep_banner, text="", bg=BG2, font=fonts.small(),
            justify="left", anchor="w", cursor="hand2")
        self.lbl_dep_banner.pack(
            fill="x", padx=12, pady=9)
        self.lbl_dep_banner.bind(
            "<Configure>",
            lambda e: self.lbl_dep_banner.configure(
                wraplength=max(1, e.width - 4)),
        )
        for w_ in (self.dep_banner, self.lbl_dep_banner):
            w_.bind("<Button-1>", lambda e: self._nb.select(self.tab_cfg))

        # Download / Stop buttons
        btn_frame = tk.Frame(p, bg=BG0)
        btn_frame.grid(row=7, column=0, padx=18, pady=(8, 0), sticky="EW")
        btn_frame.columnconfigure(0, weight=1)

        self.btn_dl = tk.Button(
            btn_frame, text="Download", bg=ACCENT, fg=ACCENT_INK,
            relief="flat", bd=0, cursor="hand2", font=fonts.button(12),
            command=self._start, highlightthickness=0,
            activebackground=ACCENT_HOVER, activeforeground=ACCENT_INK,
            disabledforeground=ACCENT_INK)
        self.btn_dl.grid(row=0, column=0, sticky="EW", ipady=12)

        self.btn_stop = tk.Button(
            btn_frame, text="Stop", bg=BG2, fg=FG0, relief="flat", bd=0,
            cursor="hand2", font=fonts.button(12),
            command=self._stop, state="disabled", highlightthickness=1,
            highlightbackground=BG3, activebackground=BG3,
            activeforeground=FG0, disabledforeground=FG2)
        self.btn_stop.grid(
            row=0, column=1, padx=(8, 0), ipady=12, ipadx=16)

        # Hairline activity sweep — invisible at rest, animates while a
        # download (or its post-processing) is running.
        self.download_activity = widgets.ActivityBar(p, bg=BG0)
        self.download_activity.grid(
            row=8, column=0, padx=18, pady=(6, 0), sticky="EW")

        # Log — a recessed "console" panel with its own header bar so
        # it reads as a distinct embedded module, not just more page.
        log_card = tk.Frame(
            p, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        log_card.grid(row=9, column=0, padx=18, pady=(10, 10), sticky="NSEW")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)

        log_head = tk.Frame(log_card, bg=BG1)
        log_head.grid(row=0, column=0, sticky="EW", padx=12, pady=(10, 6))
        log_head.columnconfigure(0, weight=1)
        tk.Label(
            log_head, text="Output log", bg=BG1, fg=FG1,
            font=fonts.body_bold(10),
        ).grid(row=0, column=0, sticky="W")
        self.btn_email_error = widgets.ghost_button(
            log_head, "✉ Email to developer", self._email_error_report,
            fg=LOG_WARN)
        self.btn_email_error.grid(row=0, column=1, ipadx=6, ipady=2)
        self.btn_email_error.grid_remove()
        widgets.ghost_button(log_head, "Clear", self._clear).grid(
            row=0, column=2, padx=(6, 0), ipadx=6, ipady=2)

        log_f = tk.Frame(log_card, bg=BG1)
        log_f.grid(row=1, column=0, sticky="NSEW", padx=12, pady=(0, 12))
        log_f.columnconfigure(0, weight=1)
        log_f.rowconfigure(0, weight=1)

        self.log = tk.Text(
            log_f, bg="#0a0a0c", fg=LOG_GRAY, state="disabled",
            relief="flat", bd=0, wrap="word", font=self._mono(), height=6,
            highlightthickness=1, highlightbackground=BG3, padx=10, pady=8)
        self.log.grid(row=0, column=0, sticky="NSEW")

        sb = tk.Scrollbar(
            log_f, command=self.log.yview, bg=BG2, troughcolor=BG1,
            activebackground=BG3)
        sb.grid(row=0, column=1, sticky="NS")
        self.log.config(yscrollcommand=sb.set)

        for tag, color in [
            ("err", LOG_RED), ("dl", LOG_GREEN), ("info", BLUE),
            ("gray", LOG_GRAY), ("blue", BLUE), ("ok", LOG_OK),
            ("fail", LOG_FAIL), ("warn", LOG_WARN),
        ]:
            self.log.tag_configure(tag, foreground=color)

        self._fmt_changed()
        self._update_dep_banner()

    # The checkbox/combobox body is the one part of this panel whose
    # height genuinely varies with how many options are turned on —
    # capping it (it scrolls internally past this height) keeps the
    # whole panel's growth bounded, so a fully expanded state never
    # pushes Destination folder / the buttons / the Output Log out of
    # the window.
    _AUDIO_BODY_CAP = 74

    def _build_audio_tools_frame(self, parent):
        """Spleeter split / click track / tempo — shown only for MP3."""
        self.split_frame = tk.Frame(
            parent, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        self.split_frame.columnconfigure(0, weight=1)

        tk.Label(
            self.split_frame, text="Audio tools", bg=BG1, fg=FG1,
            font=fonts.small_bold(),
        ).grid(row=0, column=0, padx=10, pady=(6, 2), sticky="W")

        body_row = tk.Frame(self.split_frame, bg=BG1)
        body_row.grid(row=1, column=0, sticky="EW")
        body_row.columnconfigure(0, weight=1)

        body_canvas = tk.Canvas(body_row, bg=BG1, highlightthickness=0)
        body_scroll = tk.Scrollbar(
            body_row, orient="vertical", command=body_canvas.yview,
            bg=BG2, troughcolor=BG1, activebackground=BG3)
        body_canvas.configure(yscrollcommand=body_scroll.set)
        body_canvas.grid(row=0, column=0, sticky="EW")
        body_scroll.grid(row=0, column=1, sticky="NS")

        g = tk.Frame(body_canvas, bg=BG1)
        g.columnconfigure(1, weight=1)
        canvas_window = body_canvas.create_window(
            (0, 0), window=g, anchor="nw")

        def _resize_body(_=None):
            body_canvas.configure(scrollregion=body_canvas.bbox("all"))
            needed = g.winfo_reqheight()
            body_canvas.configure(height=min(needed, self._AUDIO_BODY_CAP))
            if needed > self._AUDIO_BODY_CAP:
                body_scroll.grid()
            else:
                body_scroll.grid_remove()

        g.bind("<Configure>", _resize_body)
        body_canvas.bind(
            "<Configure>",
            lambda e: body_canvas.itemconfig(canvas_window, width=e.width))

        def _on_wheel(e):
            body_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        body_canvas.bind("<MouseWheel>", _on_wheel)
        g.bind("<MouseWheel>", _on_wheel)

        self.v_split = tk.BooleanVar()
        self.chk_split = tk.Checkbutton(
            g, text="Split audio tracks (Spleeter AI)",
            variable=self.v_split, bg=BG1, fg=FG1, selectcolor=BG2,
            activebackground=BG1, activeforeground=FG0,
            font=fonts.body(),
            command=lambda: self._on_audio_checkbox("spleeter", self.v_split))
        self.chk_split.grid(
            row=0, column=0, padx=(8, 6), pady=1, sticky="W")

        self.cbo_stems = widgets.combobox(g, list(STEM_OPTIONS))
        self.cbo_stems.grid(
            row=0, column=1, padx=(0, 8), pady=1, sticky="EW", ipady=2)

        self.v_click = tk.BooleanVar()
        self.chk_click = tk.Checkbutton(
            g, text="Generate click track (librosa)",
            variable=self.v_click, bg=BG1, fg=FG1, selectcolor=BG2,
            activebackground=BG1, activeforeground=FG0,
            font=fonts.body(),
            command=lambda: self._on_audio_checkbox("librosa", self.v_click))
        self.chk_click.grid(
            row=1, column=0, padx=(8, 6), pady=1, sticky="W")

        self.cbo_tempo_mult = widgets.combobox(g, list(TEMPO_MULTIPLIERS))
        self.cbo_tempo_mult.grid(
            row=1, column=1, padx=(0, 8), pady=1, sticky="EW", ipady=2)

        tk.Label(
            g, text="Time signature:", bg=BG1, fg=FG1, font=fonts.body(),
        ).grid(row=2, column=0, padx=(24, 6), pady=1, sticky="W")
        self.cbo_timesig = widgets.combobox(g, list(TIME_SIGNATURE_OVERRIDES))
        self.cbo_timesig.grid(
            row=2, column=1, padx=(0, 8), pady=1, sticky="EW", ipady=2)

        accents_row = tk.Frame(g, bg=BG1)
        accents_row.grid(
            row=3, column=0, columnspan=2, padx=(24, 6), pady=1, sticky="W")
        self.v_merge_click = tk.BooleanVar()
        self.chk_merge_click = tk.Checkbutton(
            accents_row, text="Merge into audio",
            variable=self.v_merge_click, bg=BG1, fg=FG1, selectcolor=BG2,
            activebackground=BG1, activeforeground=FG0,
            font=fonts.body(),
            command=self._on_merge_click_toggled)
        self.chk_merge_click.pack(side="left")

        self.v_no_accents = tk.BooleanVar()
        self.chk_no_accents = tk.Checkbutton(
            accents_row, text="No accents",
            variable=self.v_no_accents, bg=BG1, fg=FG1, selectcolor=BG2,
            activebackground=BG1, activeforeground=FG0,
            font=fonts.body(),
        )
        self.chk_no_accents.pack(side="left", padx=(16, 0))

        self.v_tempo = tk.BooleanVar()
        self.chk_tempo = tk.Checkbutton(
            g, text="Show suggested tempo (BPM)",
            variable=self.v_tempo, bg=BG1, fg=FG1, selectcolor=BG2,
            activebackground=BG1, activeforeground=FG0,
            font=fonts.body(),
            command=lambda: self._on_audio_checkbox("librosa", self.v_tempo))
        self.chk_tempo.grid(row=4, column=0, padx=(8, 6), pady=1, sticky="W")

        self.lbl_tempo_result = tk.Label(
            g, text="", bg=BG1, fg=ACCENT, font=fonts.small_bold())
        self.lbl_tempo_result.grid(row=4, column=1, padx=(0, 8), sticky="W")

        tk.Frame(self.split_frame, bg=BG3, height=1).grid(
            row=2, column=0, sticky="EW", padx=8, pady=(6, 6))

        self.btn_regenerate_click = widgets.secondary_button(
            self.split_frame, "↻ Regenerate click track…",
            self._regenerate_click_track)
        self.btn_regenerate_click.grid(
            row=3, column=0, padx=8, pady=(0, 2), sticky="EW", ipady=3)
        self.lbl_regenerate_hint = tk.Label(
            self.split_frame, bg=BG1, fg=FG2, font=fonts.small(),
            justify="left", wraplength=520,
        )
        self.lbl_regenerate_hint.grid(
            row=4, column=0, padx=8, pady=(0, 4), sticky="W")

        self.regenerate_activity = widgets.ActivityBar(self.split_frame, bg=BG1)
        self.regenerate_activity.grid(
            row=5, column=0, sticky="EW", padx=8, pady=(0, 6))

        self._update_regenerate_label()

    # ── Audio tools setup prompt ────────────────────────────────────────
    def _on_audio_checkbox(self, kind, var):
        """Called when a Spleeter/librosa-dependent checkbox is
        toggled — offer to set up the audio tools right away if they
        aren't ready yet, instead of only finding out at Download
        time."""
        if var.get():
            self._ensure_audio_tools(kind)

    def _on_merge_click_toggled(self):
        self._on_audio_checkbox("librosa", self.v_merge_click)
        self._update_regenerate_label()

    def _update_regenerate_label(self):
        """Keep the Regenerate button's label (and hint) honest about
        what it will actually produce, based on the Merge checkbox —
        so "regenerate the merged audio with the new metronome" is a
        single, obvious action rather than a hidden side effect of an
        unrelated checkbox."""
        if self.v_merge_click.get():
            self.btn_regenerate_click.config(
                text="↻ Regenerate merged audio (new metronome)…")
            self.lbl_regenerate_hint.config(
                text="Redoes the click track and re-merges it — for a "
                     "file you already downloaded.")
        else:
            self.btn_regenerate_click.config(
                text="↻ Regenerate click track…")
            self.lbl_regenerate_hint.config(
                text="For a file you already downloaded — check “Merge "
                     "into audio” above to also get a merged copy.")

    def _ensure_audio_tools(self, kind):
        dismissed = getattr(self, "_audio_prompt_dismissed", None)
        if dismissed is None:
            dismissed = {"spleeter": False, "librosa": False}
            self._audio_prompt_dismissed = dismissed
        if dismissed.get(kind):
            return

        label = (
            "Splitting audio tracks (Spleeter)" if kind == "spleeter"
            else "Tempo detection / click tracks (librosa)"
        )
        path = self.python_path

        if not path or not os.path.isfile(path):
            self._prompt_audio_tools_setup(
                kind,
                f"{label} needs a Python interpreter with audio tools "
                "installed, and none is set up yet.",
                use_embedded=True,
            )
            return

        def run():
            installed = (
                check_spleeter_installed(path) if kind == "spleeter"
                else check_librosa_installed(path)
            )
            if not installed:
                self.after(
                    0,
                    lambda: self._prompt_audio_tools_setup(
                        kind,
                        f"{label} isn't installed for the configured "
                        "Python interpreter yet.",
                        use_embedded=False,
                    ),
                )

        threading.Thread(target=run, daemon=True).start()

    def _prompt_audio_tools_setup(self, kind, reason, use_embedded):
        proceed = messagebox.askyesno(
            "Audio tools not installed",
            f"{reason}\n\n"
            "Download and set it up now? This can take a few minutes "
            "(it fetches TensorFlow/librosa).",
        )
        if not proceed:
            self._audio_prompt_dismissed[kind] = True
            return
        if use_embedded:
            self._setup_embedded_python()
        else:
            self._install_spleeter()

    def _mono(self):
        return fonts.mono_font(9)

    # ── Format change ──────────────────────────────────────────────────
    def _fmt_changed(self, _=None):
        t = FORMAT_TYPES[self.cbo_fmt.get()]
        qs = list(AUDIO_QUALITIES) if t == "audio" else list(
            VIDEO_QUALITIES)
        self.cbo_qual.config(values=qs)
        self.cbo_qual.current(0)

        if self.cbo_fmt.get() == "MP3":
            self.split_frame.grid(
                row=3, column=0, padx=18, pady=(8, 0), sticky="EW")
        else:
            self.v_split.set(False)
            self.v_click.set(False)
            self.v_merge_click.set(False)
            self.v_no_accents.set(False)
            self.v_tempo.set(False)
            self.cbo_tempo_mult.current(0)
            self.cbo_timesig.current(0)
            self.lbl_tempo_result.config(text="")
            self.split_frame.grid_remove()

    # ── Playlist warning ───────────────────────────────────────────────
    def _check_playlist_url(self, _=None):
        """Show a heads-up under the URL field when the pasted link
        points at (or includes) a playlist, since that can trigger a
        multi-file download."""
        if _is_playlist_url(self.txt_url.value()):
            self.lbl_playlist_warn.config(
                text=(
                    "⚠ This link includes a playlist — yt-dlp may "
                    "download every video in it. Set Playlist Handling "
                    "to 'Single video only' in Settings if you only "
                    "want this one."
                ),
            )
            self.lbl_playlist_warn.grid(row=1, column=0, pady=(4, 0), sticky="EW")
        else:
            self.lbl_playlist_warn.grid_remove()

    # ── Dependency reminder ────────────────────────────────────────────
    def _update_dep_banner(self):
        """Warn on the Download tab if yt-dlp/ffmpeg still need to be
        fetched."""
        ytdlp_ok = bool(self.ytdlp_path) and os.path.isfile(
            self.ytdlp_path)
        ffmpeg_ok = bool(self.ffmpeg_path) and os.path.isfile(
            self.ffmpeg_path)

        if not ytdlp_ok:
            text = (
                "⚠ yt-dlp isn't set up yet — downloads will fail. "
                "Click here or go to Settings → Dependencies to get it."
            )
            color = LOG_RED
        elif not ffmpeg_ok:
            text = (
                "⚠ ffmpeg isn't set up yet — needed to merge video/audio, "
                "extract MP3/audio formats, embed thumbnails and more. "
                "Click here or go to Settings → Dependencies to get it."
            )
            color = LOG_WARN
        else:
            self.dep_banner.grid_remove()
            return

        self.lbl_dep_banner.config(text=text, fg=color)
        self.dep_banner.config(highlightbackground=color, highlightcolor=color)
        self.dep_banner.grid(
            row=6, column=0, padx=18, pady=(16, 0), sticky="EW")

    # ── Log helpers ────────────────────────────────────────────────────
    def _log(self, text, tag="gray"):
        # Broadcast to every log widget that exists — right now that's
        # this tab's Output Log always, plus the Audio Tools tab's own
        # log when it's been built, since both tabs' actions funnel
        # through the same background-task queue.
        for widget in (self.log, getattr(self, "audio_log", None)):
            if widget is None:
                continue
            widget.config(state="normal")
            widget.insert("end", text + "\n", tag)
            widget.see("end")
            widget.config(state="disabled")

    def _clear(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self._last_error_context = None
        self.btn_email_error.grid_remove()

    # ── Error report emailing ────────────────────────────────────────
    def _email_error_report(self):
        if not smtp_config_ready():
            messagebox.showinfo(
                "Email not set up",
                "Set up SMTP first — Settings → Application → Error "
                "reporting.",
            )
            self._nb.select(self.tab_cfg)
            return
        if not messagebox.askyesno(
            "Email error report",
            "Send this failed download's log to the developer by "
            "email?\n\nIt includes the URL, format/quality, "
            "destination folder, and the full Output Log shown above.",
        ):
            return

        context = dict(self._last_error_context or {})
        log_text = self.log.get("1.0", "end")

        self.btn_email_error.config(state="disabled", text="Sending...")
        widgets.start_pulse(self.btn_email_error, weight="ghost")

        def run():
            try:
                send_error_report(context, log_text)
                self._q.put(
                    ("Error report emailed to the developer.", "ok"))
            except Exception as exc:
                self._q.put((f"Could not send error report: {exc}", "err"))
            finally:
                self.after(
                    0,
                    lambda: widgets.stop_pulse(self.btn_email_error, BG1),
                )
                self.after(
                    0,
                    lambda: self.btn_email_error.config(
                        state="normal", text="✉ Email to developer"),
                )

        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                item = self._q.get_nowait()
                if item is None:
                    self._on_done()
                elif item == "__SPLIT_DONE__":
                    self._on_split_done()
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
            if self._stop_requested:
                self._log("Stopped by user.", "warn")
                self._log("")
                self._stop_requested = False
                self._reset_buttons()
                return
            if ec == 0:
                self._log("Done — download complete.", "ok")
                needs_post = (
                    self._split_requested or self._tempo_requested
                    or self._click_requested
                )
                if needs_post and self._split_queue:
                    self._log("")
                    self._start_next_split()
                    return
                self._log("")
                self._reset_buttons()
                self._show_tip_prompt()
                return
            else:
                self._log(f"Failed — exit code {ec}.", "fail")
                self._last_error_context = {
                    **getattr(self, "_current_run_context", {}),
                    "exit_code": ec,
                }
                self.btn_email_error.grid()
        self._log("")
        self._reset_buttons()

    def _reset_buttons(self):
        widgets.stop_pulse(self.btn_dl, restore=ACCENT)
        self.download_activity.stop()
        self.btn_dl.config(state="normal", text="Download")
        self.btn_stop.config(state="disabled")

    def _stop(self):
        """Kill the running yt-dlp / audio-tools process, if any, and
        stop any further post-processing steps from starting."""
        proc = self.proc
        split_proc = getattr(self, "split_proc", None)
        if proc is None and split_proc is None:
            return
        self._stop_requested = True
        self._split_queue = []
        self.btn_stop.config(state="disabled")
        self._log("Stopping...", "warn")
        for p in (proc, split_proc):
            if p is not None:
                try:
                    p.kill()
                except Exception:
                    pass

    # ── Browse ─────────────────────────────────────────────────────────
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.txt_dest.get())
        if d:
            self.txt_dest.delete(0, "end")
            self.txt_dest.insert(0, d)

    # ── Download ───────────────────────────────────────────────────────
    def _gather_settings(self):
        return {
            "embed_thumbnail": self.v_thumb.get(),
            "embed_metadata": self.v_meta.get(),
            "embed_chapters": self.v_chapters.get(),
            "sponsorblock": self.v_sponsor.get(),
            "remux_to": self.cbo_remux.get(),
            "recode_to": self.cbo_recode.get(),
            "write_subs": self.v_subs.get(),
            "write_auto_subs": self.v_auto_subs.get(),
            "sub_langs": self.txt_sub_langs.get().strip(),
            "rate_limit": self.txt_rate.get().strip(),
            "concurrent_frags": int(self.spn_frags.get()),
            "cookies": self.cbo_cookies.get(),
            "retries": int(self.spn_retries.get()),
            "proxy": self.txt_proxy.get().strip(),
            "playlist_mode": self.v_playlist.get(),
            "out_template": (
                self.txt_tmpl.get().strip() or "%(title)s.%(ext)s"),
            "extra_args": self.txt_extra.get().strip(),
        }

    def _start(self):
        url = self.txt_url.value()
        dest = self.txt_dest.get().strip()
        fmt = self.cbo_fmt.get()
        qual = self.cbo_qual.get()

        if not url:
            messagebox.showwarning("Missing URL", "Please paste a URL first.")
            return
        if not os.path.isdir(dest):
            messagebox.showwarning(
                "Bad path", "Destination folder does not exist.")
            return
        if not self.ytdlp_path or not os.path.isfile(self.ytdlp_path):
            messagebox.showerror(
                "yt-dlp not found",
                "yt-dlp could not be located.\n\n"
                "Go to Settings → Dependencies and use Browse or "
                "Auto-detect.",
            )
            return

        if _is_playlist_url(url) and self.v_playlist.get() != "single":
            if not messagebox.askyesno(
                "Playlist detected",
                "This link appears to include a YouTube playlist. "
                "Continuing will download every video in it, which can "
                "take a while and use significant disk space.\n\n"
                "Continue and download the whole playlist?",
            ):
                return

        # A fresh attempt — any error-report offer from a previous run
        # no longer applies.
        self._current_run_context = {
            "url": url, "format": fmt, "quality": qual, "destination": dest,
        }
        self._last_error_context = None
        self.btn_email_error.grid_remove()

        s = self._gather_settings()
        args = build_args(fmt, qual, dest, url, s)

        # Without this, yt-dlp encodes its console output (filenames
        # in log lines, --print output, etc.) using the system's
        # legacy codepage once stdout is piped rather than a real
        # console — silently mangling non-ASCII titles even though the
        # file itself is saved with the correct Unicode name.
        args = ["--encoding", "utf-8"] + args

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

        self._split_requested = fmt == "MP3" and self.v_split.get()
        self._tempo_requested = fmt == "MP3" and self.v_tempo.get()
        self._merge_click_requested = fmt == "MP3" and self.v_merge_click.get()
        self._click_requested = (
            fmt == "MP3" and (self.v_click.get() or self.v_merge_click.get())
        )
        self._no_accents = fmt == "MP3" and self.v_no_accents.get()
        self._tempo_mult = float(
            TEMPO_MULTIPLIERS.get(self.cbo_tempo_mult.get(), "1"))
        self._split_queue = []
        self.lbl_tempo_result.config(text="")
        needs_python = (
            self._split_requested or self._tempo_requested
            or self._click_requested
        )
        no_python = not self.python_path or not os.path.isfile(
            self.python_path)
        if needs_python and no_python:
            messagebox.showwarning(
                "Python not found",
                "Splitting, tempo detection and click tracks need a "
                "Python interpreter with Spleeter/librosa installed.\n\n"
                "Go to Settings → Audio Tools and use ⚡ Auto-Setup "
                "Audio Tools (or Browse/Auto-detect + ↓ Install "
                "Spleeter).",
            )
            return

        self._stop_requested = False
        self.btn_dl.config(state="disabled", text="Downloading...")
        self.btn_stop.config(state="normal")
        widgets.start_pulse(self.btn_dl, weight="primary")
        self.download_activity.start()
        self._log(f"Starting: {url}", "blue")
        self._log(f"  Format  : {fmt} | {qual}", "gray")
        self._log(f"  Dest    : {dest}", "gray")
        self._log("")

        ffmpeg_ok = self.ffmpeg_path and os.path.isfile(self.ffmpeg_path)
        ffmpeg_dir = str(Path(self.ffmpeg_path).parent) if ffmpeg_ok else ""
        if ffmpeg_dir and not shutil.which("ffmpeg"):
            args = ["--ffmpeg-location", ffmpeg_dir] + args

        if needs_python:
            args = args + [
                "--print",
                f"after_move:{_SPLIT_TARGET_PREFIX}%(filepath)s",
            ]

        cmd = [self.ytdlp_path] + args

        def run():
            stale_detected = False
            try:
                flags = (
                    subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32" else 0
                )
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
                    if line.startswith(_SPLIT_TARGET_PREFIX):
                        out_path = line[
                            len(_SPLIT_TARGET_PREFIX):].strip()
                        if out_path:
                            self._split_queue.append(out_path)
                        continue
                    if any(h in line for h in _STALE_HINTS):
                        stale_detected = True
                    if "ERROR" in line or line.startswith("ERR:"):
                        tag = "err"
                    elif "[download]" in line:
                        tag = "dl"
                    elif any(
                        x in line
                        for x in ("[info]", "[youtube]", "[generic]")
                    ):
                        tag = "info"
                    else:
                        tag = "gray"
                    self._q.put((line, tag))
                self.proc.wait()
                if stale_detected and self.proc.returncode != 0:
                    self._q.put(("", "gray"))
                    self._q.put((
                        "  Hint: yt-dlp could not decrypt YouTube's "
                        "player.", "info",
                    ))
                    self._q.put((
                        "  Go to Settings → Dependencies → ↑ Update "
                        "yt-dlp", "info",
                    ))
            except Exception as exc:
                self._q.put((f"Error launching yt-dlp: {exc}", "err"))
            finally:
                self._q.put(None)

        threading.Thread(target=run, daemon=True).start()

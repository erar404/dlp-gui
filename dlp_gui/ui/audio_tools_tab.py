"""Audio Tools tab: a standalone workflow for a file you already
have — convert it, analyze its key/tempo, and generate a click track
(optionally merged into a fresh copy of the audio) — independent of
downloading anything.
"""
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

from .. import fonts, widgets
from ..constants import FORMAT_TYPES
from ..theme import (
    ACCENT, BG0, BG1, BG2, BG3, BLUE, FG1, FG2, LOG_FAIL, LOG_GRAY,
    LOG_GREEN, LOG_OK, LOG_RED, LOG_WARN,
)

# The same extensions offered on the Download tab's Format dropdown —
# picking a file here is scoped to the formats this app already knows
# how to work with.
_SELECTABLE_EXTS = sorted(
    key.lower() for key in FORMAT_TYPES if key != "Best Quality (auto)"
)
_FILETYPES = [
    ("Supported media", " ".join(f"*.{ext}" for ext in _SELECTABLE_EXTS)),
    ("All files", "*.*"),
]

# Formats the rest of this tab's tools (click-track generation,
# merging) can work with directly — anything else gets offered a
# convert-first step.
_READY_EXTS = {"mp3", "wav"}


def _no_window_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class AudioToolsTabMixin:
    """Adds the standalone Audio Tools tab to the main App window."""

    def _build_audio_tools_tab(self):
        p = self.tab_audio
        p.columnconfigure(0, weight=1)
        p.rowconfigure(9, weight=1, minsize=150)

        self._audio_file = ""

        # ── File picker ──────────────────────────────────────────────
        widgets.field_label(p, "Audio / video file", bg=BG0).grid(
            row=0, column=0, padx=18, pady=(14, 3), sticky="W")
        file_row = tk.Frame(p, bg=BG0)
        file_row.grid(row=1, column=0, padx=18, sticky="EW")
        file_row.columnconfigure(0, weight=1)
        self.txt_audio_file = widgets.entry(file_row)
        self.txt_audio_file.grid(row=0, column=0, sticky="EW", ipady=8)
        self.txt_audio_file.configure(state="readonly")
        widgets.secondary_button(
            file_row, "Browse…", self._browse_audio_tools_file,
        ).grid(row=0, column=1, padx=(8, 0), ipady=8)

        self.lbl_audio_file_info = widgets.status_label(p, bg=BG0)
        self.lbl_audio_file_info.grid(
            row=2, column=0, padx=18, pady=(4, 0), sticky="EW")
        self.lbl_audio_file_info.config(
            text="Pick a file to convert, analyze, or generate a "
                 "click track for.")

        # ── Convert (only relevant for non mp3/wav files) ───────────
        self.convert_card = tk.Frame(
            p, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        tk.Label(
            self.convert_card, text="Convert format", bg=BG1, fg=FG1,
            font=fonts.small_bold(),
        ).grid(row=0, column=0, columnspan=2, padx=10, pady=(8, 2),
               sticky="W")
        tk.Label(
            self.convert_card, bg=BG1, fg=FG2, font=fonts.small(),
            justify="left", wraplength=520,
            text="This file isn't MP3 or WAV yet — convert a copy "
                 "before analyzing it or generating a click track.",
        ).grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 8),
               sticky="W")
        self.btn_convert_mp3 = widgets.secondary_button(
            self.convert_card, "Convert to MP3",
            lambda: self._convert_audio_tools_file("mp3"))
        self.btn_convert_mp3.grid(
            row=2, column=0, padx=(10, 4), pady=(0, 10), ipady=4,
            sticky="EW")
        self.btn_convert_wav = widgets.secondary_button(
            self.convert_card, "Convert to WAV",
            lambda: self._convert_audio_tools_file("wav"))
        self.btn_convert_wav.grid(
            row=2, column=1, padx=(4, 10), pady=(0, 10), ipady=4,
            sticky="EW")
        self.convert_card.columnconfigure(0, weight=1)
        self.convert_card.columnconfigure(1, weight=1)
        self.convert_activity = widgets.ActivityBar(self.convert_card, bg=BG1)
        self.convert_activity.grid(
            row=3, column=0, columnspan=2, sticky="EW", padx=10,
            pady=(0, 8))
        self.convert_card.grid(
            row=3, column=0, padx=18, pady=(10, 0), sticky="EW")
        self.convert_card.grid_remove()

        # ── Analyze / generate ──────────────────────────────────────
        tools_card = tk.Frame(
            p, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        tools_card.grid(row=4, column=0, padx=18, pady=(10, 0), sticky="EW")
        tools_card.columnconfigure(0, weight=1)
        tk.Label(
            tools_card, text="Analyze & generate", bg=BG1, fg=FG1,
            font=fonts.small_bold(),
        ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="W")

        self.btn_analyze_audio = widgets.secondary_button(
            tools_card, "Analyze key & tempo", self._analyze_audio_tools)
        self.btn_analyze_audio.grid(
            row=1, column=0, padx=10, pady=(6, 0), ipady=5, sticky="EW")

        self.btn_click_audio = widgets.secondary_button(
            tools_card, "Generate click track",
            self._generate_click_audio_tools)
        self.btn_click_audio.grid(
            row=2, column=0, padx=10, pady=(6, 0), ipady=5, sticky="EW")

        self.btn_merge_audio = widgets.primary_button(
            tools_card, "Generate merged audio (click + original)",
            self._generate_merged_audio_tools)
        self.btn_merge_audio.grid(
            row=3, column=0, padx=10, pady=(6, 0), ipady=6, sticky="EW")

        self.lbl_audio_tools_result = tk.Label(
            tools_card, text="", bg=BG1, fg=ACCENT, font=fonts.small_bold())
        self.lbl_audio_tools_result.grid(
            row=4, column=0, padx=10, pady=(8, 0), sticky="W")

        self.audio_tools_activity = widgets.ActivityBar(tools_card, bg=BG1)
        self.audio_tools_activity.grid(
            row=5, column=0, sticky="EW", padx=10, pady=(6, 10))

        self._set_audio_tools_buttons_enabled(False)

        # ── Log — mirrors the Download tab's, and receives the same
        # broadcast messages (see DownloadTabMixin._log). ────────────
        log_card = tk.Frame(
            p, bg=BG1, highlightthickness=1, highlightbackground=BG3)
        log_card.grid(row=9, column=0, padx=18, pady=(14, 14), sticky="NSEW")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)

        log_head = tk.Frame(log_card, bg=BG1)
        log_head.grid(row=0, column=0, sticky="EW", padx=12, pady=(10, 6))
        log_head.columnconfigure(0, weight=1)
        tk.Label(
            log_head, text="Output log", bg=BG1, fg=FG1,
            font=fonts.body_bold(10),
        ).grid(row=0, column=0, sticky="W")
        widgets.ghost_button(log_head, "Clear", self._clear_audio_log).grid(
            row=0, column=1, ipadx=6, ipady=2)

        log_f = tk.Frame(log_card, bg=BG1)
        log_f.grid(row=1, column=0, sticky="NSEW", padx=12, pady=(0, 12))
        log_f.columnconfigure(0, weight=1)
        log_f.rowconfigure(0, weight=1)

        self.audio_log = tk.Text(
            log_f, bg="#0a0a0c", fg=LOG_GRAY, state="disabled",
            relief="flat", bd=0, wrap="word", font=self._mono(), height=6,
            highlightthickness=1, highlightbackground=BG3, padx=10, pady=8)
        self.audio_log.grid(row=0, column=0, sticky="NSEW")

        sb = tk.Scrollbar(
            log_f, command=self.audio_log.yview, bg=BG2, troughcolor=BG1,
            activebackground=BG3)
        sb.grid(row=0, column=1, sticky="NS")
        self.audio_log.config(yscrollcommand=sb.set)

        for tag, color in [
            ("err", LOG_RED), ("dl", LOG_GREEN), ("info", BLUE),
            ("gray", LOG_GRAY), ("blue", BLUE), ("ok", LOG_OK),
            ("fail", LOG_FAIL), ("warn", LOG_WARN),
        ]:
            self.audio_log.tag_configure(tag, foreground=color)

    def _clear_audio_log(self):
        self.audio_log.config(state="normal")
        self.audio_log.delete("1.0", "end")
        self.audio_log.config(state="disabled")

    # ── File selection ──────────────────────────────────────────────
    def _set_audio_tools_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for btn in (
            self.btn_analyze_audio, self.btn_click_audio,
            self.btn_merge_audio,
        ):
            btn.config(state=state)

    def _browse_audio_tools_file(self):
        initial_dir = self.txt_dest.get().strip() or str(Path.home())
        path = filedialog.askopenfilename(
            title="Pick an audio or video file",
            initialdir=initial_dir if os.path.isdir(initial_dir) else None,
            filetypes=_FILETYPES,
        )
        if not path:
            return
        self._set_audio_tools_file(path)

    def _set_audio_tools_file(self, path: str):
        self._audio_file = path
        self.txt_audio_file.configure(state="normal")
        self.txt_audio_file.delete(0, "end")
        self.txt_audio_file.insert(0, path)
        self.txt_audio_file.configure(state="readonly")
        self.lbl_audio_tools_result.config(text="")

        ext = os.path.splitext(path)[1].lstrip(".").lower()
        if ext in _READY_EXTS:
            self.lbl_audio_file_info.config(
                text=f"✓ .{ext} — ready to analyze or generate a click "
                     "track directly.", fg=LOG_OK)
            self.convert_card.grid_remove()
        else:
            self.lbl_audio_file_info.config(
                text=f"⚠ .{ext} isn't MP3 or WAV — convert a copy first.",
                fg=LOG_WARN)
            self.convert_card.grid()
        self._set_audio_tools_buttons_enabled(True)

    # ── Convert ──────────────────────────────────────────────────────
    def _convert_audio_tools_file(self, target_ext: str):
        if not self._audio_file:
            return
        if not self.ffmpeg_path or not os.path.isfile(self.ffmpeg_path):
            messagebox.showwarning(
                "ffmpeg not set",
                "Converting needs ffmpeg — Settings → Dependencies.")
            return

        src = self._audio_file
        base = os.path.splitext(os.path.basename(src))[0]
        dest_dir = os.path.dirname(src)
        out_path = os.path.join(dest_dir, f"{base}.{target_ext}")

        for btn in (self.btn_convert_mp3, self.btn_convert_wav):
            btn.config(state="disabled")
        widgets.start_pulse(self.btn_convert_mp3, weight="secondary")
        widgets.start_pulse(self.btn_convert_wav, weight="secondary")
        self.convert_activity.start()
        self._q.put((
            f"Converting to {target_ext.upper()}: "
            f"{os.path.basename(src)}", "blue",
        ))

        def run():
            try:
                cmd = [self.ffmpeg_path, "-y", "-i", src]
                if target_ext == "mp3":
                    cmd += ["-codec:a", "libmp3lame", "-qscale:a", "2"]
                cmd.append(out_path)
                r = subprocess.run(
                    cmd, capture_output=True, text=True,
                    creationflags=_no_window_flags(),
                )
                if r.returncode == 0 and os.path.isfile(out_path):
                    self._q.put((f"Converted: {out_path}", "ok"))
                    self.after(
                        0, lambda: self._set_audio_tools_file(out_path))
                else:
                    tail = "\n".join((r.stderr or "").splitlines()[-5:])
                    self._q.put((
                        "Conversion failed — ffmpeg exit code "
                        f"{r.returncode}.", "fail",
                    ))
                    if tail:
                        self._q.put((tail, "err"))
            except Exception as exc:
                self._q.put((f"Error converting file: {exc}", "err"))
            finally:
                self.after(0, self.convert_activity.stop)
                self.after(
                    0,
                    lambda: widgets.stop_pulse(self.btn_convert_mp3, BG2),
                )
                self.after(
                    0,
                    lambda: widgets.stop_pulse(self.btn_convert_wav, BG2),
                )
                self.after(
                    0,
                    lambda: [
                        b.config(state="normal")
                        for b in (self.btn_convert_mp3, self.btn_convert_wav)
                    ],
                )

        threading.Thread(target=run, daemon=True).start()

    # ── Analyze / generate ──────────────────────────────────────────
    def _run_audio_tools_action(
        self, *, click_requested, merge_requested, button, busy_text,
        idle_text, weight,
    ):
        if not self._audio_file or not os.path.isfile(self._audio_file):
            messagebox.showwarning(
                "No file selected", "Pick a file first.")
            return
        if not self.python_path or not os.path.isfile(self.python_path):
            messagebox.showwarning(
                "Python not set",
                "Audio tools need a configured Python interpreter "
                "first — Settings → Audio Tools.")
            return
        if not self.ffmpeg_path or not os.path.isfile(self.ffmpeg_path):
            messagebox.showwarning(
                "ffmpeg not set",
                "This needs ffmpeg — Settings → Dependencies.")
            return

        audio_file = self._audio_file
        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        dest_dir = os.path.dirname(audio_file)
        idle_bg = ACCENT if weight == "primary" else BG2

        self._set_audio_tools_buttons_enabled(False)
        button.config(text=busy_text)
        widgets.start_pulse(button, weight=weight)
        self.audio_tools_activity.start()

        def progress(text):
            button.config(text=text)

        def run():
            try:
                self._run_click_analysis(
                    audio_file, dest_dir, base_name,
                    click_requested=click_requested,
                    merge_requested=merge_requested,
                    progress_cb=progress,
                    result_label=self.lbl_audio_tools_result,
                )
            finally:
                self.after(0, self.audio_tools_activity.stop)
                self.after(
                    0, lambda: widgets.stop_pulse(button, idle_bg))
                self.after(0, lambda: button.config(text=idle_text))
                self.after(
                    0, lambda: self._set_audio_tools_buttons_enabled(True))

        threading.Thread(target=run, daemon=True).start()

    def _analyze_audio_tools(self):
        self._run_audio_tools_action(
            click_requested=False, merge_requested=False,
            button=self.btn_analyze_audio, busy_text="Analyzing...",
            idle_text="Analyze key & tempo", weight="secondary")

    def _generate_click_audio_tools(self):
        self._run_audio_tools_action(
            click_requested=True, merge_requested=False,
            button=self.btn_click_audio,
            busy_text="Generating click track...",
            idle_text="Generate click track", weight="secondary")

    def _generate_merged_audio_tools(self):
        self._run_audio_tools_action(
            click_requested=True, merge_requested=True,
            button=self.btn_merge_audio,
            busy_text="Generating merged audio...",
            idle_text="Generate merged audio (click + original)",
            weight="primary")

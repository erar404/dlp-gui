"""Download tab: URL entry, format/quality pickers, audio tools
checkboxes, the Download button, and the output log.
"""
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..constants import (
    AUDIO_QUALITIES, FORMAT_TYPES, STEM_OPTIONS, VIDEO_QUALITIES,
)
from ..theme import (
    BG0, BG1, BG2, BG3, BLUE, FG0, FG1, FG2, LOG_FAIL, LOG_GRAY,
    LOG_GREEN, LOG_OK, LOG_RED, LOG_WARN, RED,
)
from ..widgets import PlaceholderEntry
from ..ytdlp_args import build_args

_STALE_HINTS = [
    "nsig extraction failed",
    "Precondition check failed",
    "Only images are available",
]


class DownloadTabMixin:
    """Adds the Download tab and its behavior to the main App window."""

    # ── UI construction ───────────────────────────────────────────────
    def _build_download(self):
        p = self.tab_dl
        p.columnconfigure(0, weight=1)
        p.rowconfigure(9, weight=1)   # log row expands

        # URL
        tk.Label(
            p, text="YouTube / Video URL", bg=BG0, fg=FG1,
            font=("Segoe UI", 10),
        ).grid(row=0, column=0, padx=16, pady=(14, 3), sticky="W")
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
        tk.Label(
            fq, text="Format", bg=BG0, fg=FG1, font=("Segoe UI", 10),
        ).grid(row=0, column=0, sticky="W")
        tk.Label(
            fq, text="Quality / Resolution", bg=BG0, fg=FG1,
            font=("Segoe UI", 10),
        ).grid(row=0, column=1, padx=(10, 0), sticky="W")
        self.cbo_fmt = ttk.Combobox(
            fq, values=list(FORMAT_TYPES), state="readonly",
            font=("Segoe UI", 9))
        self.cbo_fmt.grid(row=1, column=0, sticky="EW", ipady=2, pady=(3, 0))
        self.cbo_fmt.current(0)
        self.cbo_qual = ttk.Combobox(
            fq, values=list(VIDEO_QUALITIES), state="readonly",
            font=("Segoe UI", 9))
        self.cbo_qual.grid(
            row=1, column=1, sticky="EW", padx=(10, 0), ipady=2, pady=(3, 0))
        self.cbo_qual.current(0)
        self.cbo_fmt.bind("<<ComboboxSelected>>", self._fmt_changed)

        self._build_audio_tools_frame(p)

        # Destination
        tk.Label(
            p, text="Destination Folder", bg=BG0, fg=FG1,
            font=("Segoe UI", 10),
        ).grid(row=4, column=0, padx=16, pady=(10, 3), sticky="W")
        dest = tk.Frame(p, bg=BG0)
        dest.grid(row=5, column=0, padx=16, sticky="EW")
        dest.columnconfigure(0, weight=1)
        self.txt_dest = tk.Entry(
            dest, bg=BG2, fg=FG0, insertbackground=FG0,
            relief="solid", bd=1, font=("Segoe UI", 9))
        self.txt_dest.insert(0, str(Path.home() / "Videos"))
        self.txt_dest.grid(row=0, column=0, sticky="EW", ipady=5)
        tk.Button(
            dest, text="Browse...", bg=BG2, fg=FG0, relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI", 9), command=self._browse,
            highlightthickness=1, highlightbackground=BG3,
            activebackground=BG3, activeforeground=FG0,
        ).grid(row=0, column=1, padx=(6, 0), ipady=5)

        # Dependency reminder — warns before downloading if yt-dlp/ffmpeg
        # aren't ready
        self.lbl_dep_banner = tk.Label(
            p, text="", bg=BG0, font=("Segoe UI", 9), justify="left",
            anchor="w", cursor="hand2")
        self.lbl_dep_banner.bind(
            "<Configure>",
            lambda e: self.lbl_dep_banner.configure(
                wraplength=max(1, e.width - 4)),
        )
        self.lbl_dep_banner.bind(
            "<Button-1>", lambda e: self._nb.select(self.tab_cfg))

        # Download button
        self.btn_dl = tk.Button(
            p, text="Download", bg=RED, fg=FG0, relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI Semibold", 11),
            command=self._start, highlightthickness=1,
            highlightbackground=RED, activebackground="#b91c1c",
            activeforeground=FG0)
        self.btn_dl.grid(
            row=7, column=0, padx=16, pady=(10, 0), sticky="EW", ipady=10)

        # Log
        tk.Label(
            p, text="Output Log", bg=BG0, fg=FG1, font=("Segoe UI", 10),
        ).grid(row=8, column=0, padx=16, pady=(12, 3), sticky="W")
        log_f = tk.Frame(p, bg=BG0)
        log_f.grid(row=9, column=0, padx=16, sticky="NSEW")
        log_f.columnconfigure(0, weight=1)
        log_f.rowconfigure(0, weight=1)

        self.log = tk.Text(
            log_f, bg="#0a0a0a", fg=LOG_GRAY, state="disabled",
            relief="flat", bd=0, wrap="word", font=self._mono())
        self.log.grid(row=0, column=0, sticky="NSEW")

        sb = tk.Scrollbar(
            log_f, command=self.log.yview, bg=BG2, troughcolor=BG1,
            activebackground=BG3)
        sb.grid(row=0, column=1, sticky="NS")
        self.log.config(yscrollcommand=sb.set)

        for tag, color in [
            ("err", LOG_RED), ("dl", LOG_GREEN), ("info", BLUE),
            ("gray", LOG_GRAY), ("blue", BLUE), ("ok", LOG_OK),
            ("fail", LOG_FAIL),
        ]:
            self.log.tag_configure(tag, foreground=color)

        # Clear log
        tk.Button(
            p, text="Clear log", bg=BG1, fg=FG2, relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI", 8), command=self._clear,
            highlightthickness=1, highlightbackground=BG2,
            activebackground=BG3, activeforeground=FG0,
        ).grid(row=10, column=0, padx=16, pady=(4, 10), sticky="EW")

        self._fmt_changed()
        self._update_dep_banner()

    def _build_audio_tools_frame(self, parent):
        """Spleeter split / click track / tempo — shown only for MP3."""
        self.split_frame = tk.Frame(
            parent, bg=BG0, highlightthickness=1, highlightbackground=BG3)
        self.split_frame.columnconfigure(1, weight=1)

        self.v_split = tk.BooleanVar()
        self.chk_split = tk.Checkbutton(
            self.split_frame, text="Split audio tracks (Spleeter AI)",
            variable=self.v_split, bg=BG0, fg=FG1, selectcolor=BG2,
            activebackground=BG0, activeforeground=FG0,
            font=("Segoe UI", 10))
        self.chk_split.grid(
            row=0, column=0, padx=(8, 6), pady=(8, 2), sticky="W")

        self.cbo_stems = ttk.Combobox(
            self.split_frame, values=list(STEM_OPTIONS), state="readonly",
            font=("Segoe UI", 9))
        self.cbo_stems.grid(
            row=0, column=1, padx=(0, 8), pady=(8, 2), sticky="EW", ipady=2)
        self.cbo_stems.current(0)

        self.v_click = tk.BooleanVar()
        self.chk_click = tk.Checkbutton(
            self.split_frame, text="Generate click track (librosa)",
            variable=self.v_click, bg=BG0, fg=FG1, selectcolor=BG2,
            activebackground=BG0, activeforeground=FG0,
            font=("Segoe UI", 10))
        self.chk_click.grid(
            row=1, column=0, columnspan=2, padx=(8, 6), pady=2, sticky="W")

        self.v_tempo = tk.BooleanVar()
        self.chk_tempo = tk.Checkbutton(
            self.split_frame, text="Show suggested tempo (BPM)",
            variable=self.v_tempo, bg=BG0, fg=FG1, selectcolor=BG2,
            activebackground=BG0, activeforeground=FG0,
            font=("Segoe UI", 10))
        self.chk_tempo.grid(
            row=2, column=0, padx=(8, 6), pady=(2, 8), sticky="W")

        self.lbl_tempo_result = tk.Label(
            self.split_frame, text="", bg=BG0, fg=BLUE,
            font=("Segoe UI", 9, "bold"))
        self.lbl_tempo_result.grid(
            row=2, column=1, padx=(0, 8), pady=(2, 8), sticky="W")

    def _mono(self):
        try:
            import tkinter.font as tkf
            if "Cascadia Code" in tkf.families():
                return ("Cascadia Code", 8)
            return ("Consolas", 9)
        except Exception:
            return ("Consolas", 9)

    # ── Format change ──────────────────────────────────────────────────
    def _fmt_changed(self, _=None):
        t = FORMAT_TYPES[self.cbo_fmt.get()]
        qs = list(AUDIO_QUALITIES) if t == "audio" else list(
            VIDEO_QUALITIES)
        self.cbo_qual.config(values=qs)
        self.cbo_qual.current(0)

        if self.cbo_fmt.get() == "MP3":
            self.split_frame.grid(
                row=3, column=0, padx=16, pady=(10, 0), sticky="EW")
        else:
            self.v_split.set(False)
            self.v_click.set(False)
            self.v_tempo.set(False)
            self.lbl_tempo_result.config(text="")
            self.split_frame.grid_remove()

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
            self.lbl_dep_banner.grid_remove()
            return

        self.lbl_dep_banner.config(text=text, fg=color)
        self.lbl_dep_banner.grid(
            row=6, column=0, padx=16, pady=(10, 0), sticky="EW")

    # ── Log helpers ────────────────────────────────────────────────────
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
                self.btn_dl.config(state="normal", text="Download")
                self._show_tip_prompt()
                return
            else:
                self._log(f"Failed — exit code {ec}.", "fail")
        self._log("")
        self.btn_dl.config(state="normal", text="Download")

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
                "yt-dlp.exe could not be located.\n\n"
                "Go to Settings → Dependencies and use Browse or "
                "Auto-detect.",
            )
            return

        s = self._gather_settings()
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

        self._split_requested = fmt == "MP3" and self.v_split.get()
        self._tempo_requested = fmt == "MP3" and self.v_tempo.get()
        self._click_requested = fmt == "MP3" and self.v_click.get()
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

        self.btn_dl.config(state="disabled", text="Downloading...")
        self._log(f"Starting: {url}", "blue")
        self._log(f"  Format  : {fmt} | {qual}", "gray")
        self._log(f"  Dest    : {dest}", "gray")
        self._log("")

        ffmpeg_ok = self.ffmpeg_path and os.path.isfile(self.ffmpeg_path)
        ffmpeg_dir = str(Path(self.ffmpeg_path).parent) if ffmpeg_ok else ""
        if ffmpeg_dir and not shutil.which("ffmpeg"):
            args = ["--ffmpeg-location", ffmpeg_dir] + args

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
                    needs_post = (
                        self._split_requested or self._tempo_requested
                        or self._click_requested
                    )
                    if needs_post and "[ExtractAudio] Destination:" in line:
                        out_path = line.split("Destination:", 1)[1].strip()
                        self._split_queue.append(out_path)
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

"""Main application window — combines all the tab/feature mixins."""
import queue
import sys
import tkinter as tk
from tkinter import ttk

from . import fonts
from .audio_tools import AudioToolsMixin
from .dependencies import (
    extract_bundled, find_embedded_python, find_ffmpeg, find_python,
    find_ytdlp,
)
from .paths import load_config
from .theme import ACCENT, BG0, BG1, BG2, BG3, FG0, FG1
from .tip_jar import TipJarMixin
from .ui.download_tab import DownloadTabMixin
from .ui.settings_tab import SettingsTabMixin

extract_bundled()
_cfg = load_config()
YT_DLP = _cfg.get("ytdlp_path") or find_ytdlp()
FFMPEG = _cfg.get("ffmpeg_path") or find_ffmpeg()
PYTHON_PATH = (
    _cfg.get("python_path") or find_embedded_python() or find_python()
)


class App(
    tk.Tk, DownloadTabMixin, SettingsTabMixin, AudioToolsMixin, TipJarMixin,
):
    def __init__(self):
        super().__init__()
        self.title("DLP-UI")
        self.geometry("760x860")
        self.minsize(680, 560)
        self.configure(bg=BG0)
        self.proc = None
        self.split_proc = None
        self._q = queue.Queue()
        self.ytdlp_path = YT_DLP
        self.ffmpeg_path = FFMPEG
        self.python_path = PYTHON_PATH
        self._split_requested = False
        self._tempo_requested = False
        self._click_requested = False
        self._merge_click_requested = False
        self._no_accents = False
        self._tempo_mult = 1.0
        self._split_queue = []
        self._stop_requested = False
        self._build()
        self._poll()

    # ── UI construction ───────────────────────────────────────────────
    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TNotebook", background=BG0, borderwidth=0, tabmargins=0)
        style.configure(
            "TNotebook.Tab", background=BG1, foreground=FG1,
            padding=[20, 12], font=fonts.body(10), borderwidth=0)
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG0)],
            foreground=[("selected", ACCENT), ("!selected", FG1)])

        style.configure(
            "TCombobox", fieldbackground=BG2, background=BG2,
            foreground=FG0, selectbackground=BG2, selectforeground=FG0,
            arrowcolor=FG1, bordercolor=BG3, lightcolor=BG2,
            darkcolor=BG2, insertcolor=FG0, padding=4)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BG2)],
            background=[("readonly", BG2)],
            foreground=[("readonly", FG0)],
            bordercolor=[("focus", ACCENT)])
        self.option_add("*TCombobox*Listbox.background", BG2)
        self.option_add("*TCombobox*Listbox.foreground", FG0)
        self.option_add(
            "*TCombobox*Listbox.selectBackground", BG3)
        self.option_add("*TCombobox*Listbox.font", fonts.body(10))

        self._nb = nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_dl = tk.Frame(nb, bg=BG0)
        self.tab_cfg = tk.Frame(nb, bg=BG0)
        nb.add(self.tab_dl, text="Download")
        nb.add(self.tab_cfg, text="Settings")

        self._build_download()
        self._build_settings()

        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ── Scrolling ──────────────────────────────────────────────────────
    def _on_tab_changed(self, _=None):
        if self._nb.index(self._nb.select()) == 1:
            self.bind_all("<MouseWheel>", self._scroll_cfg)
        else:
            self.unbind_all("<MouseWheel>")

    def _scroll_cfg(self, e):
        # macOS reports small per-notch deltas (±1..3); Windows reports
        # multiples of 120.
        step = e.delta if sys.platform == "darwin" else e.delta / 120
        self._cfg_canvas.yview_scroll(int(-1 * step), "units")

    def on_close(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.destroy()

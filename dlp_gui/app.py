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
from .paths import BASE, load_config
from .theme import ACCENT, BG0, BG1, BG2, BG3, FG0, FG1
from .tip_jar import TipJarMixin
from .ui.audio_tools_tab import AudioToolsTabMixin
from .ui.download_tab import DownloadTabMixin
from .ui.settings_tab import SettingsTabMixin


def _detach_from_python_taskbar_group():
    """Windows groups a running script's taskbar button under whatever
    process launched it (python.exe) unless the process claims its own
    "Application User Model ID" — without this, the taskbar shows
    python.exe's generic icon instead of the window's own icon (set
    below via iconbitmap), even though the title bar shows it
    correctly since that's a separate, per-window property. A no-op
    when frozen (the compiled .exe is already its own distinct
    process) or on non-Windows platforms."""
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "erar404.mdtools.downloader")
    except Exception:
        pass


_detach_from_python_taskbar_group()

extract_bundled()
_cfg = load_config()
YT_DLP = _cfg.get("ytdlp_path") or find_ytdlp()
FFMPEG = _cfg.get("ffmpeg_path") or find_ffmpeg()
PYTHON_PATH = (
    _cfg.get("python_path") or find_embedded_python() or find_python()
)

# The comfortable, designed-for size — used as-is on any screen roomy
# enough for it, and scaled down on smaller ones (see _fit_to_screen).
DESIGN_WIDTH, DESIGN_HEIGHT = 760, 860
MIN_WIDTH, MIN_HEIGHT = 680, 560


class App(
    tk.Tk, DownloadTabMixin, SettingsTabMixin, AudioToolsMixin,
    AudioToolsTabMixin, TipJarMixin,
):
    def __init__(self):
        super().__init__()
        self.title("MD Tools")
        self._set_icon()
        self._fit_to_screen()
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
        self._current_run_context = {}
        self._last_error_context = None
        self._build()
        self._poll()

    # ── Window chrome ────────────────────────────────────────────────
    def _set_icon(self):
        """Give the window (and so its taskbar/minimized representation)
        the app's own icon instead of Tk's generic default one.

        iconbitmap's .ico support is Windows-only; it's a no-op
        elsewhere (macOS gets its icon from the .app bundle itself —
        see dlp-ui-macos.spec).
        """
        try:
            self.iconbitmap(str(BASE / "favicon.ico"))
        except Exception:
            pass

    def _fit_to_screen(self):
        """Use the designed size on any screen roomy enough for it;
        scale down (and re-center) on smaller ones instead of
        overflowing off-screen or getting clipped by the taskbar."""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Leave headroom for taskbars/docks/menu bars around the edges.
        max_w = int(screen_w * 0.92)
        max_h = int(screen_h * 0.88)

        width = min(DESIGN_WIDTH, max_w)
        height = min(DESIGN_HEIGHT, max_h)

        min_w = min(MIN_WIDTH, width)
        min_h = min(MIN_HEIGHT, height)
        self.minsize(min_w, min_h)

        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

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
        self.tab_audio = tk.Frame(nb, bg=BG0)
        self.tab_cfg = tk.Frame(nb, bg=BG0)
        nb.add(self.tab_dl, text="Download")
        nb.add(self.tab_audio, text="Audio Tools")
        nb.add(self.tab_cfg, text="Settings")

        self._build_download()
        self._build_audio_tools_tab()
        self._build_settings()

        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ── Scrolling ──────────────────────────────────────────────────────
    def _on_tab_changed(self, _=None):
        # Compared by widget identity, not index, so tab order can
        # change without this silently scrolling the wrong pane.
        if self._nb.select() == str(self.tab_cfg):
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

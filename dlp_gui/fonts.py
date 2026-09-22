"""Cross-platform type scale.

Family lookups need a live Tk root (tkinter.font.families() reads from
it), so resolution is lazy — cached on first call, not done at import
time, since these modules get imported before the App's root exists.
"""
import sys

if sys.platform == "win32":
    _DISPLAY_CANDIDATES = ["Segoe UI Semibold", "Segoe UI"]
    _TEXT_CANDIDATES = ["Segoe UI"]
    _MONO_CANDIDATES = ["Cascadia Code", "Consolas"]
elif sys.platform == "darwin":
    _DISPLAY_CANDIDATES = ["SF Pro Display", "Helvetica Neue"]
    _TEXT_CANDIDATES = ["SF Pro Text", "Helvetica Neue"]
    _MONO_CANDIDATES = ["SF Mono", "Menlo"]
else:
    _DISPLAY_CANDIDATES = ["Inter", "DejaVu Sans"]
    _TEXT_CANDIDATES = ["Inter", "DejaVu Sans"]
    _MONO_CANDIDATES = ["JetBrains Mono", "DejaVu Sans Mono"]

_cache = {}


def _pick(candidates, fallback):
    key = tuple(candidates)
    if key in _cache:
        return _cache[key]
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families())
    except Exception:
        available = set()
    chosen = next((c for c in candidates if c in available), fallback)
    _cache[key] = chosen
    return chosen


def text():
    """Body/label family — used for the great majority of UI text."""
    return _pick(_TEXT_CANDIDATES, "TkDefaultFont")


def display():
    """Heavier family for titles/section headers, where available."""
    return _pick(_DISPLAY_CANDIDATES, text())


def mono():
    return _pick(_MONO_CANDIDATES, "TkFixedFont")


# ── Semantic scale ───────────────────────────────────────────────────────
def title(size=15):
    return (display(), size, "bold")


def section(size=12):
    """Card/group headers."""
    return (display(), size, "bold")


def category(size=11):
    """Super-headers grouping several cards (e.g. 'Setup')."""
    return (display(), size, "bold")


def body(size=10):
    return (text(), size)


def body_bold(size=10):
    return (text(), size, "bold")


def label(size=10):
    return (text(), size)


def small(size=9):
    return (text(), size)


def small_bold(size=9):
    return (text(), size, "bold")


def button(size=10):
    return (text(), size, "bold")


def mono_font(size=9):
    return (mono(), size)

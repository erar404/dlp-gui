"""Detecting and provisioning yt-dlp, ffmpeg, and the portable Python
runtime used for Spleeter / librosa audio tools.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import BASE

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# Windows ships every dependency as a bare .exe; macOS/Linux binaries
# carry no extension.
EXE = ".exe" if IS_WINDOWS else ""


def _mac_arch() -> str:
    """python-build-standalone's macOS asset naming: 'aarch64' on
    Apple Silicon, 'x86_64' on Intel."""
    return "aarch64" if platform.machine() in ("arm64", "aarch64") else "x86_64"


YTDLP_RELEASE_URL = {
    "win32": (
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
        "yt-dlp.exe"
    ),
    "darwin": (
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
        "yt-dlp_macos"
    ),
}.get(
    sys.platform,
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
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
    str(Path.home() / "AppData" / "Local" / "Programs" / "yt-dlp"
        / "yt-dlp.exe"),
    str(Path.home() / "AppData" / "Local" / "yt-dlp" / "yt-dlp.exe"),
    str(BASE / "yt-dlp" / "yt-dlp.exe"),
    str(BASE / "yt-dlp.exe"),
    # macOS / Homebrew / Linux
    "/opt/homebrew/bin/yt-dlp",
    "/usr/local/bin/yt-dlp",
    "/usr/bin/yt-dlp",
    str(Path.home() / ".local" / "bin" / "yt-dlp"),
    str(BASE / "yt-dlp" / "yt-dlp"),
    str(BASE / "yt-dlp"),
]

COMMON_FFMPEG_PATHS = [
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    str(Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe"),
    str(Path.home() / "AppData" / "Local" / "Programs" / "ffmpeg" / "bin"
        / "ffmpeg.exe"),
    str(BASE / "ffmpeg" / "ffmpeg.exe"),
    str(BASE / "ffmpeg.exe"),
    # macOS / Homebrew / Linux
    "/opt/homebrew/bin/ffmpeg",
    "/opt/homebrew/opt/ffmpeg/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/local/opt/ffmpeg/bin/ffmpeg",
    "/usr/bin/ffmpeg",
    str(BASE / "ffmpeg" / "ffmpeg"),
    str(BASE / "ffmpeg"),
]

# Spleeter only ships wheels for Python 3.6-3.10 (needs the stdlib
# `distutils` module, removed in 3.12+), so it gets its own private,
# portable interpreter — the user never has to install Python
# system-wide.
EMBED_PYTHON_VERSION = "3.10.11"
EMBED_PYTHON_URL_WINDOWS = (
    f"https://www.python.org/ftp/python/{EMBED_PYTHON_VERSION}/"
    f"python-{EMBED_PYTHON_VERSION}-embed-amd64.zip"
)

# macOS has no equivalent "embeddable zip" from python.org, so the
# portable runtime there comes from python-build-standalone instead —
# fully relocatable, self-contained CPython builds meant for exactly
# this (bundling a private interpreter in an app). Pinned to a known-
# good release rather than "latest" so the download URL doesn't shift
# under us.
EMBED_PYTHON_VERSION_MACOS = "3.10.21"
EMBED_PYTHON_BUILD_TAG_MACOS = "20260901"
EMBED_PYTHON_URL_MACOS = (
    "https://github.com/astral-sh/python-build-standalone/releases/"
    f"download/{EMBED_PYTHON_BUILD_TAG_MACOS}/"
    f"cpython-{EMBED_PYTHON_VERSION_MACOS}+{EMBED_PYTHON_BUILD_TAG_MACOS}"
    f"-{_mac_arch()}-apple-darwin-install_only.tar.gz"
)

EMBED_PYTHON_URL = EMBED_PYTHON_URL_MACOS if IS_MACOS else EMBED_PYTHON_URL_WINDOWS

GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def _no_window_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def find_ytdlp() -> str:
    """Return the first valid yt-dlp executable path, or empty string."""
    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / f"yt-dlp{EXE}"
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
        p = Path(sys._MEIPASS) / "ffmpeg" / f"ffmpeg{EXE}"
        if p.exists():
            return str(p)
    for p in COMMON_FFMPEG_PATHS:
        if os.path.isfile(p):
            return p
    return ""


def find_python() -> str:
    """Return the first usable Python interpreter path, or empty string."""
    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def find_embedded_python() -> str:
    """Return the app's private, portable Python interpreter path, or
    empty string if it hasn't been set up yet."""
    if IS_MACOS:
        p = BASE / "python-embed" / "bin" / "python3"
    else:
        p = BASE / "python-embed" / "python.exe"
    return str(p) if p.is_file() else ""


def check_spleeter_installed(python_path: str) -> bool:
    """Return True if Spleeter (and the TensorFlow it depends on)
    actually loads.

    A bare `import spleeter` isn't enough — spleeter's package
    __init__ doesn't import TensorFlow eagerly, so it can report
    "installed" even when TensorFlow is broken (e.g. a numpy 2.x /
    TensorFlow 1.x-ABI mismatch) and separation would fail the moment
    it actually runs.
    """
    if not python_path or not os.path.isfile(python_path):
        return False
    try:
        r = subprocess.run(
            [python_path, "-c", "from spleeter.separator import Separator"],
            capture_output=True, text=True, timeout=60,
            creationflags=_no_window_flags(),
        )
        return r.returncode == 0
    except Exception:
        return False


def check_librosa_installed(python_path: str) -> bool:
    """Return True if librosa + soundfile (tempo detection / click
    tracks) load under the given interpreter."""
    if not python_path or not os.path.isfile(python_path):
        return False
    try:
        r = subprocess.run(
            [python_path, "-c", "import librosa, soundfile"],
            capture_output=True, text=True, timeout=30,
            creationflags=_no_window_flags(),
        )
        return r.returncode == 0
    except Exception:
        return False


def extract_bundled() -> None:
    """Copy deps bundled inside the PyInstaller EXE next to it on first
    launch."""
    if not getattr(sys, "frozen", False):
        return
    bundle = Path(sys._MEIPASS)
    pairs = [
        (bundle / f"yt-dlp{EXE}", BASE / "yt-dlp" / f"yt-dlp{EXE}"),
        (bundle / "ffmpeg" / f"ffmpeg{EXE}",
         BASE / "ffmpeg" / f"ffmpeg{EXE}"),
        (bundle / "ffmpeg" / f"ffprobe{EXE}",
         BASE / "ffmpeg" / f"ffprobe{EXE}"),
    ]
    for src, dst in pairs:
        try:
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                if not IS_WINDOWS:
                    dst.chmod(dst.stat().st_mode | 0o111)
        except Exception:
            pass  # Non-fatal — sys._MEIPASS fallback still works

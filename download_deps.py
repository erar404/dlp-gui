"""Download build-time dependencies into deps/, ready to bundle into
the packaged app.

Windows: yt-dlp.exe + ffmpeg.exe + ffprobe.exe are all downloaded and
bundled directly into the exe (see dlp-ui.spec) — a fully self-
contained, portable build.

macOS: only yt-dlp is downloaded/bundled (deps/yt-dlp, see
dlp-ui-macos.spec). A copied Homebrew ffmpeg binary depends on
Homebrew's shared libraries at their Homebrew install paths, so it
can't be bundled the same way a static Windows .exe can — the app
finds/installs ffmpeg via Homebrew at runtime instead (Settings →
Dependencies → Get ffmpeg).
"""
import os
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

IS_MACOS = sys.platform == "darwin"

YTDLP_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
    + ("yt-dlp_macos" if IS_MACOS else "yt-dlp.exe")
)
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-lgpl.zip"
)

deps = Path("deps")
deps.mkdir(exist_ok=True)


def _hook(label):
    def hook(count, block_size, total_size):
        done = count * block_size
        if total_size > 0:
            pct = min(100, done * 100 // total_size)
            mb = done / 1_048_576
            tmb = total_size / 1_048_576
            print(
                f"  {label}: {mb:.1f}/{tmb:.1f} MB ({pct}%)   ",
                end="\r", flush=True,
            )
    return hook


# ── yt-dlp ───────────────────────────────────────────────────────────────
ytdlp = deps / ("yt-dlp" if IS_MACOS else "yt-dlp.exe")
if ytdlp.exists():
    print(f"{ytdlp.name}  already in deps/  [skip]")
else:
    print("Downloading yt-dlp...")
    try:
        urllib.request.urlretrieve(YTDLP_URL, str(ytdlp), _hook("yt-dlp"))
        if IS_MACOS:
            ytdlp.chmod(ytdlp.stat().st_mode | stat.S_IEXEC
                        | stat.S_IXGRP | stat.S_IXOTH)
        print(f"\n  OK -> {ytdlp}")
    except Exception as e:
        print(f"\n  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

# ── ffmpeg ───────────────────────────────────────────────────────────────
if IS_MACOS:
    print()
    print(
        "Skipping ffmpeg — not bundled on macOS. The app finds or "
        "installs it via Homebrew at runtime (Settings → Dependencies "
        "→ Get ffmpeg). Install it yourself first with "
        "'brew install ffmpeg' if you'd rather not rely on that."
    )
else:
    ffmpeg = deps / "ffmpeg.exe"
    ffprobe = deps / "ffprobe.exe"
    if ffmpeg.exists() and ffprobe.exists():
        print("ffmpeg.exe  already in deps/  [skip]")
    else:
        print("Downloading ffmpeg (may take a moment)...")
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".zip", delete=False
            ) as f:
                tmp = f.name
            urllib.request.urlretrieve(FFMPEG_URL, tmp, _hook("ffmpeg"))
            print("\n  Extracting...")
            with zipfile.ZipFile(tmp) as zf:
                for member in zf.namelist():
                    name = member.split("/")[-1]
                    if name in ("ffmpeg.exe", "ffprobe.exe"):
                        dest = deps / name
                        dest.write_bytes(zf.read(member))
                        print(f"  -> {dest}")
            print("  OK")
        except Exception as e:
            print(f"\n  ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

print()
print("Deps ready:")
expected = ["yt-dlp"] if IS_MACOS else ["yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe"]
for f in expected:
    p = deps / f
    if p.exists():
        print(f"  deps/{f}  ({p.stat().st_size // 1024} KB)")
    else:
        print(f"  deps/{f}  MISSING", file=sys.stderr)
        sys.exit(1)

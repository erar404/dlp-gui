"""Download build dependencies (yt-dlp.exe, ffmpeg.exe, ffprobe.exe) into deps/."""
import urllib.request
import zipfile
import os
import sys
import tempfile
from pathlib import Path

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
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
            mb  = done / 1_048_576
            tmb = total_size / 1_048_576
            print(f"  {label}: {mb:.1f}/{tmb:.1f} MB ({pct}%)   ", end="\r", flush=True)
    return hook


# ── yt-dlp ────────────────────────────────────────────────────────────────────
ytdlp = deps / "yt-dlp.exe"
if ytdlp.exists():
    print("yt-dlp.exe  already in deps/  [skip]")
else:
    print("Downloading yt-dlp...")
    try:
        urllib.request.urlretrieve(YTDLP_URL, str(ytdlp), _hook("yt-dlp"))
        print(f"\n  OK -> {ytdlp}")
    except Exception as e:
        print(f"\n  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

# ── ffmpeg ────────────────────────────────────────────────────────────────────
ffmpeg  = deps / "ffmpeg.exe"
ffprobe = deps / "ffprobe.exe"
if ffmpeg.exists() and ffprobe.exists():
    print("ffmpeg.exe  already in deps/  [skip]")
else:
    print("Downloading ffmpeg (may take a moment)...")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
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
for f in ("yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe"):
    p = deps / f
    if p.exists():
        print(f"  deps\\{f}  ({p.stat().st_size // 1024} KB)")
    else:
        print(f"  deps\\{f}  MISSING", file=sys.stderr)
        sys.exit(1)

#!/bin/sh
# DLP-UI macOS build script — produces dist/dlp-ui.app (and a zip of it,
# named to match the in-app self-updater's expected asset name).
set -e

echo "=== DLP-UI macOS Build Script ==="
echo

if [ "$(uname -s)" != "Darwin" ]; then
    echo "ERROR: this script builds the macOS app and must run on macOS."
    exit 1
fi

# ── Python ──────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3 (e.g. 'brew install"
    echo "python') and try again."
    exit 1
fi

# ── PyInstaller + Pillow (icon conversion) ─────────────────────────────
if ! python3 -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller not found. Installing..."
    python3 -m pip install --user pyinstaller
fi
if ! python3 -c "import PIL" >/dev/null 2>&1; then
    echo "Pillow not found (needed to build the app icon). Installing..."
    python3 -m pip install --user pillow
fi

# ── ffmpeg (build-machine only — see download_deps.py for why it isn't
#    bundled) ─────────────────────────────────────────────────────────
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo
    echo "NOTE: ffmpeg isn't on PATH. It won't be bundled into the app"
    echo "either way (see download_deps.py) — end users get it via"
    echo "Settings -> Dependencies -> Get ffmpeg (Homebrew) on first run."
    echo "Install it now with 'brew install ffmpeg' if you want to smoke-"
    echo "test merging/remuxing after this build."
    echo
fi

# ── Bundled deps (yt-dlp) ───────────────────────────────────────────────
python3 download_deps.py

# ── App icon (.icns from favicon.ico) ───────────────────────────────────
if [ ! -f icon.icns ]; then
    echo "Building icon.icns from favicon.ico..."
    ICONSET=$(mktemp -d)/AppIcon.iconset
    mkdir -p "$ICONSET"
    python3 - "$ICONSET" <<'PYEOF'
import sys
from PIL import Image

iconset = sys.argv[1]

# .ico files can hold several embedded sizes — Pillow's ICO plugin
# reports them via .info["sizes"]; render everything from the largest.
probe = Image.open("favicon.ico")
sizes = probe.info.get("sizes") or [probe.size]
largest = max(sizes, key=lambda s: s[0])
base = Image.open("favicon.ico")
base.size = largest
base = base.convert("RGBA")

# (filename, pixel dimension) pairs an .iconset expects.
targets = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]
for name, px in targets:
    base.resize((px, px), Image.LANCZOS).save(f"{iconset}/{name}")
PYEOF
    iconutil -c icns "$ICONSET" -o icon.icns
    rm -rf "$(dirname "$ICONSET")"
    echo "  -> icon.icns"
fi

# ── Build ─────────────────────────────────────────────────────────────
echo "Building dlp-ui.app..."
python3 -m PyInstaller dlp-ui-macos.spec

echo
if [ -d "dist/dlp-ui.app" ]; then
    echo "Build successful: dist/dlp-ui.app"

    ARCH=$(uname -m)
    case "$ARCH" in
        arm64) ASSET_ARCH=arm64 ;;
        x86_64) ASSET_ARCH=x86_64 ;;
        *) ASSET_ARCH="$ARCH" ;;
    esac
    ZIP_NAME="dlp-ui-macos-${ASSET_ARCH}.zip"
    echo "Zipping for release as dist/${ZIP_NAME}..."
    (cd dist && rm -f "${ZIP_NAME}" && ditto -c -k --sequesterRsrc \
        --keepParent dlp-ui.app "${ZIP_NAME}")
    echo "  -> dist/${ZIP_NAME}"
else
    echo "Build may have failed. Check the output above."
    exit 1
fi

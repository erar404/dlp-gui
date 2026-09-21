<div align="center">

# <span style="color:#dc2626">DLP-UI</span>

<span style="color:#666">A dark-themed GUI wrapper for yt-dlp — download any video or audio with one click</span>

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![tkinter](https://img.shields.io/badge/UI-tkinter-informational)](https://docs.python.org/3/library/tkinter.html)
[![yt-dlp](https://img.shields.io/badge/backend-yt--dlp-red)](https://github.com/yt-dlp/yt-dlp)
[![PyInstaller](https://img.shields.io/badge/build-PyInstaller-brightgreen)](https://pyinstaller.org)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows)](https://microsoft.com/windows)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Tech Stack](#-tech-stack)
- [Features](#-features)
- [UI Tabs / Screens](#-ui-tabs--screens)
- [Project Structure](#-project-structure)
- [Setup & Installation](#-setup--installation)
- [Running the App](#-running-the-app)
- [Building for Production](#-building-for-production)
- [yt-dlp Path Detection](#-yt-dlp-path-detection)
- [Config Persistence](#-config-persistence)
- [Backend API](#-backend-api)
- [Core Data Flow](#-core-data-flow)
- [Format Selection Logic](#-format-selection-logic)
- [Brand & Design Tokens](#-brand--design-tokens)
- [License](#-license)

---

## 🎯 Overview

**DLP-UI** is a lightweight, portable Windows GUI that wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) — the most capable video downloader available. Instead of memorising command-line flags, users paste a URL, pick a format and quality, and click Download. All yt-dlp options (subtitles, SponsorBlock, remux, proxy, cookies, custom templates) are surfaced as controls.

The app ships in two forms that are functionally identical:

| Implementation | File | Runtime |
|---|---|---|
| Python / tkinter | `dlp-ui.py` | Python 3.8 + (or compiled `.exe`) |
| PowerShell / WinForms | `dlp-ui.ps1` | Windows PowerShell 5.1+ |

The Python version is the primary build target and adds **yt-dlp path auto-detection**, **config persistence**, and a larger log area.

> 💡 **Design philosophy:** zero install friction. Drop the `.exe` next to `yt-dlp.exe` or point the app at wherever yt-dlp lives on each machine. No registry, no installer.

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.8 + |
| GUI toolkit | tkinter (stdlib) | bundled with Python |
| Process execution | subprocess (stdlib) | bundled with Python |
| Config storage | json (stdlib) | bundled with Python |
| Executable detection | shutil.which (stdlib) | bundled with Python |
| Build tool | PyInstaller | latest (`pip install pyinstaller`) |
| Alt UI runtime | PowerShell / System.Windows.Forms | Windows built-in |
| Video backend | yt-dlp | external binary (any recent build) |

---

## ✨ Features

### 🎬 Video Download

- **11 formats**: Best Quality (auto), MP4, MKV, WebM, MP3, M4A, AAC, FLAC, WAV, OPUS, OGG
- **7 quality levels**: Best available, 4K (2160p), 1440p, 1080p, 720p, 480p, 360p
- **5 audio bitrates** (when an audio format is selected): Best (VBR), 320 Kbps, 256 Kbps, 192 Kbps, 128 Kbps
- Quality dropdown automatically switches between video resolution and audio bitrate when the format type changes

### 🎛️ Post-Processing

- Embed thumbnail as cover art (`--embed-thumbnail`)
- Embed metadata — title, artist, etc. (`--embed-metadata`)
- Embed chapter markers (`--embed-chapters`)
- SponsorBlock: remove all sponsored segments (`--sponsorblock-remove all`)
- Remux to a different container without re-encoding (MP4, MKV, MOV, WebM, AVI, FLV)
- Re-encode to a new format (MP4, MKV, MOV, WebM, MP3, M4A, WAV)

### 📝 Subtitles

- Download subtitles (`--write-subs`)
- Include auto-generated subtitles (`--write-auto-subs`)
- Language filter — comma-separated codes, e.g. `en,ja`

### 🌐 Network

- Rate limit (e.g. `5M`, `500K`)
- Concurrent fragments (1–32, maps to `-N`)
- Cookies from browser — Chrome, Firefox, Edge, Brave, Opera, Safari, Vivaldi, Chromium
- Retry count (1–50, default 10)
- Proxy support (e.g. `socks5://127.0.0.1:1080`)

### 📂 Playlist Handling

- **Auto** — let yt-dlp decide based on the URL
- **Single video only** (`--no-playlist`)
- **Always download full playlist** (`--yes-playlist`)

### 📄 Output

- Custom filename template using yt-dlp format strings (default: `%(title)s.%(ext)s`)
- Browse for destination folder
- Extra raw yt-dlp flags appended verbatim

### 🎚️ Audio Tools (Spleeter · Click Track · Tempo)

When **MP3** is selected as the format, three extra options appear:

- **Split audio tracks (Spleeter AI)** — uses [Deezer's Spleeter](https://github.com/deezer/spleeter) to separate the downloaded MP3 into isolated stems after the download finishes
  - Stem presets: **2 stems** (vocals / instrumental), **4 stems** (vocals / drums / bass / other), **5 stems** (+ piano)
  - Output stems are written to a `<filename>_tracks` subfolder next to the downloaded MP3 (e.g. `Song Title_tracks\vocals.wav`)
- **Generate click track (librosa)** — analyzes the downloaded MP3 with [librosa](https://librosa.org/)'s beat tracker and renders a metronome click at every detected beat, encoded to `<filename>_click.mp3` next to the source file (via ffmpeg)
- **Show suggested tempo (BPM)** — runs the same beat-tracking analysis and displays the estimated tempo (e.g. `128.4 BPM`) next to the checkbox, and logs it to the Output Log

**No Python installation required on the target machine.** Settings → **Audio Tools (Spleeter · Click Track · Tempo)** → **⚡ Auto-Setup Audio Tools** downloads a private, portable Python 3.10 runtime (the official embeddable build from python.org) into `python-embed/` next to the app, bootstraps `pip` inside it, and installs Spleeter + librosa there — completely isolated from any Python already on the system. This runtime is never shared with or visible to other applications.

- Spleeter needs Python 3.6–3.10 specifically (it depends on an old TensorFlow/numpy pin that has no prebuilt wheels for 3.11+, and building from source fails because `numpy.distutils` relies on the standard-library `distutils` module removed in Python 3.12) — the portable runtime sidesteps this entirely, and librosa/soundfile are installed into the same runtime so tempo/click-track features share it
- The download is sizeable (~500 MB+, mostly TensorFlow) and only happens once, on demand
- Advanced users who already have a compatible Python 3.6–3.10 install can instead point the app at it directly (Browse/Auto-detect + ↓ Install Spleeter) under "Advanced" in the same settings group

### 🔍 yt-dlp Executable Location

- **Auto-detect** scans `PATH` and 6 common Windows install locations
- **Browse** opens a file picker to navigate to `yt-dlp.exe` anywhere on disk
- Chosen path persists to `dlp-ui-config.json` and reloads on next launch
- Status indicator shows green "Found: …" or red "Not found: …" in real time

### ☕ Tip Jar

- A small popup appears after every successful download, with a lighthearted note (`TIP_NOTE` in `dlp-ui.py` — one string, edit it freely) and the developer's tip QR code (`qrcode.png`) underneath
- Purely cosmetic — closing it does nothing to the app; there's nothing to unlock

---

## 🖥️ UI Tabs / Screens

The app is a fixed-size (660 × 700) dark window with two tabs.

### 📥 Download Tab

```
┌─────────────────────────────────────────────────────────────┐
│  YouTube / Video URL                                        │
│  [ Paste a link here...                                   ] │
│                                                             │
│  Format              Quality / Resolution                   │
│  [ MP4           ▼]  [ 1080p                           ▼]  │
│                                                             │
│  Destination Folder                                         │
│  [ C:\Users\…\Videos                          ] [Browse…]  │
│                                                             │
│  [            Download            ]  ← red accent button   │
│                                                             │
│  Output Log                                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Starting: https://…                                 │  │
│  │  [download] 45.2% of 123.4MiB at 2.10MiB/s …       │  │
│  │  Done — download complete.                           │  │
│  └──────────────────────────────────────────────────────┘  │
│  [ Clear log ]                                              │
└─────────────────────────────────────────────────────────────┘
```

### ⚙️ Settings Tab

```
┌─────────────────────────────────────────────────────────────┐
│  yt-dlp Executable                                          │
│  [ C:\ERAR\yt-dlp\dist\yt-dlp.exe    ] [Browse…][Auto-det] │
│  ✓ Found: C:\ERAR\yt-dlp\dist\yt-dlp.exe                   │
│                                                             │
│  Post-Processing                                            │
│  ☐ Embed thumbnail   ☐ Embed metadata   ☐ Embed chapters   │
│  ☐ SponsorBlock      Remux to: [None▼]  Re-encode: [None▼] │
│                                                             │
│  Subtitles                                                  │
│  ☐ Download subs   ☐ Auto-generated    Languages: [en    ] │
│                                                             │
│  Network                                                    │
│  Rate limit: [     ]  Fragments: [1▲]  Cookies: [None  ▼]  │
│  Retries: [10▲]  Proxy: [                               ]  │
│                                                             │
│  Playlist Handling                                          │
│  ◉ Auto   ○ Single video only   ○ Always full playlist     │
│                                                             │
│  Output Filename Template                                   │
│  [ %(title)s.%(ext)s                                      ] │
│                                                             │
│  Extra yt-dlp Arguments                                     │
│  [                                                        ] │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

The Python/tkinter app is a package (`dlp_gui/`) with a thin entry
point (`dlp-ui.py`), organized by function so each concern lives in
its own module:

```
dlp-ui/
├── dlp-ui.py                   # Entry point — imports App and runs mainloop
│
├── dlp_gui/                    # The actual implementation
│   ├── theme.py                #   Dark color palette (BG0, FG0, LOG_*, ...)
│   ├── constants.py            #   Format tables, STEM_OPTIONS, TIP_NOTES,
│   │                           #   TEMPO_CLICK_SCRIPT, version/URL strings
│   ├── paths.py                #   BASE dir, config load/save, resource_path()
│   ├── dependencies.py         #   find_ytdlp/ffmpeg/python, Spleeter/librosa
│   │                           #   health checks, extract_bundled()
│   ├── ytdlp_args.py           #   build_args() — UI state → yt-dlp CLI flags
│   ├── widgets.py              #   PlaceholderEntry (tk.Entry subclass)
│   ├── audio_tools.py          #   AudioToolsMixin — Spleeter split, tempo
│   │                           #   detection, click-track generation
│   ├── tip_jar.py              #   TipJarMixin — the post-download tip popup
│   ├── app.py                  #   App(tk.Tk, *Mixins) — window + wiring
│   │
│   └── ui/
│       ├── download_tab.py     #   DownloadTabMixin — Download tab + _start()
│       └── settings_tab.py     #   SettingsTabMixin — Settings tab, all
│                                #   dependency/update management
│
├── dlp-ui.ps1                  # Alternate implementation — PowerShell/WinForms
│                                #   Identical feature set; yt-dlp path is hardcoded
│
├── DLP-UI.bat                  # Launcher — runs dlp-ui.ps1 via powershell.exe
│
├── build.bat                   # One-click PyInstaller build → dist\dlp-ui.exe
├── dlp-ui.spec                 # PyInstaller spec (--onefile --windowed, UPX on)
├── setup.cfg                   # flake8 config (max-line-length = 99)
│
├── dlp-ui-config.json          # Runtime config (created on first use, not in repo)
│                                #   Stores: ytdlp_path, ffmpeg_path, python_path
│
├── dist/
│   └── dlp-ui.exe               # Compiled standalone executable (build output)
│
└── build/                       # PyInstaller intermediate artefacts (safe to delete)
```

Each module in `dlp_gui/` only imports what it needs from its
siblings (e.g. `ui/download_tab.py` imports `STEM_OPTIONS` from
`constants.py`, not the other way around) — there are no circular
imports. `App` in `app.py` combines the `DownloadTabMixin`,
`SettingsTabMixin`, `AudioToolsMixin` and `TipJarMixin` classes via
multiple inheritance so the Tkinter widgets each tab creates
(`self.txt_url`, `self.btn_dl`, etc.) remain on one shared `self`
across all of them, exactly as they were in the original single-file
version — this was a pure reorganization, not a behavior change.

---

## 🚀 Setup & Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| Windows 10 / 11 | Required for WinForms launcher; tkinter build runs anywhere Python does |
| Python 3.8 + | Only needed to run `dlp-ui.py` directly or to build the exe |
| yt-dlp | Download from [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases) |
| ffmpeg (optional) | Required for remux, re-encode, thumbnail embedding, and SponsorBlock |

### Clone / Download

```bash
git clone https://github.com/yourname/dlp-ui.git
cd dlp-ui
```

Or download the ZIP from the releases page and extract it anywhere.

### Python dependencies

`dlp-ui.py` uses only the Python standard library — **no `pip install` needed** to run the script directly.

To build the standalone `.exe`:

```bash
pip install pyinstaller
```

---

## ▶️ Running the App

### Option 1 — Compiled executable (recommended)

```
dist\dlp-ui.exe
```

No Python required. The exe is fully self-contained.

### Option 2 — Python script directly

```bash
python dlp-ui.py
```

Or with the system Python launcher on Windows:

```bash
py dlp-ui.py
```

### Option 3 — PowerShell WinForms version

Double-click `DLP-UI.bat`, or run from a terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File dlp-ui.ps1
```

> ⚠️ The PowerShell version has a hardcoded yt-dlp path (`C:\ERAR\yt-dlp\dist\yt-dlp.exe`). Use the Python version for cross-device portability.

---

## 📦 Building for Production

`build.bat` automates the entire process:

```batch
build.bat
```

What it does:

1. Checks whether `pyinstaller` is on `PATH`; installs it via `pip` if not
2. Runs: `py -m PyInstaller --onefile --windowed --name "dlp-ui" dlp-ui.py`
3. Reports success or failure

Output:

```
dist\dlp-ui.exe     ← single portable executable (~10–15 MB with UPX)
```

To rebuild manually using the saved spec:

```bash
pyinstaller dlp-ui.spec
```

PyInstaller options baked into the spec:

| Option | Value | Effect |
|---|---|---|
| `--onefile` | true | Single `.exe`, no folder |
| `--windowed` | true | No console window on launch |
| `--name` | `dlp-ui` | Output filename |
| `upx` | true | UPX compression applied to binary |
| `console` | false | Suppresses black terminal window |

> 📌 `dlp-ui-config.json` is created at runtime next to the `.exe` — it is not bundled into the binary.

---

## 🔍 yt-dlp Path Detection

The Python version finds `yt-dlp.exe` automatically at startup using a priority chain:

```
1. dlp-ui-config.json  →  "ytdlp_path" key (saved from a previous session)
          ↓ not found
2. shutil.which("yt-dlp") / shutil.which("yt-dlp.exe")  →  system PATH
          ↓ not found
3. Common install locations (checked in order):
     C:\ERAR\yt-dlp\dist\yt-dlp.exe
     C:\Program Files\yt-dlp\yt-dlp.exe
     C:\Program Files (x86)\yt-dlp\yt-dlp.exe
     %USERPROFILE%\yt-dlp\yt-dlp.exe
     %USERPROFILE%\AppData\Local\Programs\yt-dlp\yt-dlp.exe
     %USERPROFILE%\AppData\Local\yt-dlp\yt-dlp.exe
     <same folder as dlp-ui.exe>\yt-dlp.exe
          ↓ not found
4. Path left empty — user must use Browse or Auto-detect in Settings
```

### Setting the path from the UI

In the **Settings** tab, under **yt-dlp Executable**:

- **Browse…** — opens a file picker filtered to `*.exe`
- **Auto-detect** — reruns the detection chain and fills the path if found
- You can also type or paste a path directly into the entry; commit it with Enter or by clicking away

Any path set via the UI is immediately saved to `dlp-ui-config.json` so it persists across restarts.

---

## 💾 Config Persistence

`dlp-ui-config.json` is created next to `dlp-ui.py` (or `dlp-ui.exe` when compiled). It is plain JSON and safe to edit manually.

**Location:**

| Run mode | Config file location |
|---|---|
| `python dlp-ui.py` | Same directory as `dlp-ui.py` |
| `dist\dlp-ui.exe` | Same directory as `dlp-ui.exe` |

**Schema:**

```json
{
  "ytdlp_path": "C:\\ERAR\\yt-dlp\\dist\\yt-dlp.exe",
  "ffmpeg_path": "C:\\ffmpeg\\ffmpeg.exe",
  "python_path": "C:\\Python310\\python.exe"
}
```

| Key | Type | Description |
|---|---|---|
| `ytdlp_path` | string | Absolute path to `yt-dlp.exe` chosen by the user or auto-detected |
| `ffmpeg_path` | string | Absolute path to `ffmpeg.exe` chosen by the user or auto-detected |
| `python_path` | string | Absolute path to the Python interpreter used to run Spleeter for audio splitting |

> 💡 To reset to auto-detection on next launch, delete `dlp-ui-config.json` or clear the `ytdlp_path` value.

---

## 🌍 Backend API

The production backend is deployed on **Google Cloud Run** (asia-southeast1).

| Property | Value |
|---|---|
| Base URL | `https://rgmc-bc-api-prod-935246372408.asia-southeast1.run.app/` |
| Provider | Google Cloud Run |
| Region | `asia-southeast1` (Singapore) |

> 📌 Task-authenticated endpoints require a secret passed as an auth header/param. Keep the task secret out of source control — store it in an environment variable or a local config file that is `.gitignore`d.

---

## 🔄 Core Data Flow

A download from URL to disk follows this path:

```
User pastes URL
      │
      ▼
[Download] button clicked
      │
      ├─ Validates: URL non-empty, dest folder exists, yt-dlp exe exists
      │
      ▼
build_args(fmt, quality, dest, url, settings)
      │
      ├─ Selects -f format selector string based on container + quality
      ├─ Appends post-processing flags (--embed-thumbnail, etc.)
      ├─ Appends subtitle flags
      ├─ Appends network flags (--limit-rate, -N, --cookies-from-browser, etc.)
      ├─ Appends playlist mode flag (--no-playlist / --yes-playlist)
      └─ Appends -o <dest>\%(title)s.%(ext)s <url>
      │
      ▼
subprocess.Popen([yt-dlp.exe] + args,
    stdout=PIPE, stderr=STDOUT,
    creationflags=CREATE_NO_WINDOW)
      │
      ▼
Background thread reads stdout line-by-line
      │
      ├─ Classifies each line: err / dl / info / gray
      └─ Pushes (line, tag) onto queue.Queue
      │
      ▼
UI timer (200 ms) drains queue
      │
      └─ Appends colored text to log widget
      │
      ▼
proc.wait() → None sentinel pushed to queue
      │
      ▼
_on_done() → shows "Done" (green) or "Failed (exit N)" (red)
             re-enables Download button
```

---

## ⚙️ Format Selection Logic

`build_args()` translates the UI format + quality pair into yt-dlp `-f` selectors:

### 🎬 Video formats

| Format | Quality set? | `-f` argument |
|---|---|---|
| Best Quality (auto) | any | `bestvideo+bestaudio/best` |
| MP4 | yes (e.g. 1080p) | `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/…` |
| MP4 | no | `bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best` |
| MKV | yes | `bestvideo[height<=N]+bestaudio/best[height<=N]` |
| WebM | yes | `bestvideo[height<=N][ext=webm]+bestaudio[ext=webm]/best[height<=N]` |

### 🎵 Audio formats

```
-f bestaudio -x --audio-format <codec> --audio-quality <bitrate>
```

| Format | codec flag | Bitrate example |
|---|---|---|
| MP3 | `mp3` | `320K` |
| M4A | `m4a` | `0` (VBR best) |
| AAC | `aac` | `192K` |
| FLAC | `flac` | `0` (lossless) |
| WAV | `wav` | `0` |
| OPUS | `opus` | `256K` |
| OGG | `vorbis` | `128K` |

---

## 🎨 Brand & Design Tokens

The dark theme is consistent across both the Python and PowerShell implementations.

### Color Palette

| Token | Hex | RGB | Usage |
|---|---|---|---|
| `BG0` | `#121212` | 18, 18, 18 | Window background |
| `BG1` | `#1c1c1c` | 28, 28, 28 | Tab bar background, Clear log button |
| `BG2` | `#282828` | 40, 40, 40 | Input fields, Browse buttons |
| `BG3` | `#373737` | 55, 55, 55 | Button borders, spinbox buttons |
| `FG0` | `#ffffff` | 255, 255, 255 | Primary text, field values |
| `FG1` | `#aaaaaa` | 170, 170, 170 | Labels |
| `FG2` | `#6e6e6e` | 110, 110, 110 | Placeholder text, group headings |
| `RED` | `#dc2626` | 220, 38, 38 | Download button (primary CTA) |
| `BLUE` | `#64a0ff` | 100, 160, 255 | Info log lines, URL echo |

### Log Line Colors

| Tag | Hex | Trigger |
|---|---|---|
| `err` / red | `#ff6464` | Lines containing `ERROR` or starting with `ERR:` |
| `dl` / green | `#64dc64` | Lines containing `[download]` |
| `info` / blue | `#64a0ff` | Lines containing `[info]`, `[youtube]`, `[generic]` |
| `gray` | `#d2d2d2` | All other lines |
| `ok` | `#50dc50` | "Done — download complete." |
| `fail` | `#ff5050` | "Failed — exit code N." |

### Typography

| Context | Font | Size |
|---|---|---|
| UI labels, controls | Segoe UI | 9 pt |
| Download button | Segoe UI Semibold | 11 pt |
| Log output | Cascadia Code (fallback: Consolas) | 8 pt |

---

## 📄 License

This project is for personal / private use. No license file is currently included in the repository. All rights reserved by the author.

> ⚠️ **yt-dlp** is a separate project licensed under the Unlicense. Downloading copyrighted content without authorization may violate the terms of service of the source platform and applicable law. Use responsibly.

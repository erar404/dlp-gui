"""Static app data: version info, format tables, and canned text."""

VERSION = "1.0.0"
GITHUB_REPO = "erar404/dlp-gui"
APP_RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
)

VIDEO_QUALITIES = {
    "Best available": "",
    "4K (2160p)": "[height<=2160]",
    "1440p": "[height<=1440]",
    "1080p": "[height<=1080]",
    "720p": "[height<=720]",
    "480p": "[height<=480]",
    "360p": "[height<=360]",
}

AUDIO_QUALITIES = {
    "Best (VBR)": "0",
    "320 Kbps": "320K",
    "256 Kbps": "256K",
    "192 Kbps": "192K",
    "128 Kbps": "128K",
}

FORMAT_TYPES = {
    "Best Quality (auto)": "video",
    "MP4": "video",
    "MKV": "video",
    "WebM": "video",
    "MP3": "audio",
    "M4A": "audio",
    "AAC": "audio",
    "FLAC": "audio",
    "WAV": "audio",
    "OPUS": "audio",
    "OGG": "audio",
}

# ── Spleeter (AI audio splitter) ────────────────────────────────────────
STEM_OPTIONS = {
    "2 Stems — Vocals / Instrumental": "2",
    "4 Stems — Vocals / Drums / Bass / Other": "4",
    "5 Stems — + Piano": "5",
}

# Instrument names Spleeter writes one file per, for each stem count —
# needed to stitch chunked output back together (see audio_tools.py).
STEM_INSTRUMENTS = {
    "2": ["vocals", "accompaniment"],
    "4": ["vocals", "drums", "bass", "other"],
    "5": ["vocals", "drums", "bass", "piano", "other"],
}

# Spleeter (on CPU, on Windows, with this TensorFlow build) reliably
# crashes with a native STATUS_STACK_BUFFER_OVERRUN (0xC0000409) when
# asked to separate more than a few minutes of audio in one pass —
# confirmed: 60s and 180s succeed, ~600s (its own default duration cap)
# crashes, regardless of stem count. Audio longer than this gets
# processed in sequential chunks and stitched back together instead.
SPLEETER_CHUNK_SECONDS = 120

# Run under the same portable interpreter as Spleeter (librosa/soundfile
# are installed alongside it).
# Invoked as: python -c TEMPO_CLICK_SCRIPT <audio> <0|1> [click_wav_out]
# Prints "TEMPO:<bpm>" and, when a click track was requested,
# "CLICK_WRITTEN:<path>".
TEMPO_CLICK_SCRIPT = r"""
import sys
import numpy as np
import librosa
import soundfile as sf

audio_path = sys.argv[1]
want_click = len(sys.argv) > 2 and sys.argv[2] == "1"
click_out = sys.argv[3] if len(sys.argv) > 3 else ""

y, sr = librosa.load(audio_path, sr=None, mono=True)
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
tempo = float(np.ravel(tempo)[0])
print(f"TEMPO:{tempo:.1f}")

if want_click and click_out:
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    clicks = librosa.clicks(times=beat_times, sr=sr, length=len(y))
    sf.write(click_out, clicks, sr)
    print(f"CLICK_WRITTEN:{click_out}")
"""

# ── Tip jar ──────────────────────────────────────────────────────────────
# Shown after every successful download — one is picked at random each
# time. Edit freely, add more, remove some — it's just a list of strings.
TIP_NOTES = [
    "Well, that download didn't torrent itself.\n\n"
    "If this app just saved you from 14 sketchy \"free downloader\" "
    "sites, 3 pop-up ads, and a fake \"Your PC is infected!\" warning "
    "— consider tossing the developer a tip. It won't unlock any "
    "features, because there's nothing to unlock. It's just nice.\n\n"
    "No pressure though — the Download button will keep working "
    "either way.",

    "ya, pembarya ya pangkain lang",

    "ser pangkape lang po",

    "God Bless you kapatid. Pwede ka rin mag LO dito. hahaha",

    "Para Sayo to, Rene",

    "Ser Tapos na po. Luma na rubber shoes ko.",

    "God Loves a cheerful giver",

    "Ui QR code, try mo scan tas lagay mo 500",
]

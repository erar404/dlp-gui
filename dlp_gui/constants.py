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

# Manual correction for the metronome's speed — beat trackers commonly
# make "octave errors" (locking onto half or double the true tempo), so
# this lets the user override the detected tempo directly rather than
# fight the detector. Affects both the click track and the displayed
# BPM; key/time-signature detection are unaffected.
TEMPO_MULTIPLIERS = {
    "1x (as detected)": "1",
    "2x (double time)": "2",
    "1/2x (half time)": "0.5",
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
# Invoked as:
#   python -c TEMPO_CLICK_SCRIPT <audio> <0|1> [click_wav_out] \
#       [tempo_mult] [no_accents 0|1] [min_bpm] [max_bpm] [tightness]
# tempo_mult manually corrects for beat-tracker "octave errors" (locking
# onto half/double the true tempo) — 1 (default), 2, or 0.5.
# min_bpm/max_bpm bias and then constrain the detected tempo to a
# plausible range for the material (also octave-error correction, just
# automatic instead of manual); tightness controls how rigidly the
# beat tracker follows a steady grid vs. loosely following the audio's
# actual onsets (librosa default: 100).
# Prints "TEMPO:<bpm>" (already adjusted by tempo_mult),
# "KEY:<root> <major|minor>", "TIMESIG:<n>/<d>", and, when a click track
# was requested, "CLICK_WRITTEN:<path>".
TEMPO_CLICK_SCRIPT = r"""
import sys
import numpy as np
import librosa
import soundfile as sf

audio_path = sys.argv[1]
want_click = len(sys.argv) > 2 and sys.argv[2] == "1"
click_out = sys.argv[3] if len(sys.argv) > 3 else ""
tempo_mult = float(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else 1.0
no_accents = len(sys.argv) > 5 and sys.argv[5] == "1"
min_bpm = float(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else 60.0
max_bpm = float(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7] else 200.0
tightness = float(sys.argv[8]) if len(sys.argv) > 8 and sys.argv[8] else 100.0
if min_bpm > max_bpm:
    min_bpm, max_bpm = max_bpm, min_bpm

y, sr = librosa.load(audio_path, sr=None, mono=True)

# --- Tempo ---------------------------------------------------------------
# beat_track's per-beat positions can drift, double, or skip on
# real-world audio, so only its single overall tempo estimate is
# trusted here — the click track below is built on a perfectly even
# grid at that one tempo instead of the raw, sometimes-irregular
# beat_frames, so the metronome never skips or wanders off-tempo.
#
# start_bpm seeds the search at the middle of the user's tempo range,
# and tightness controls how strictly the tracker holds a steady grid
# vs. loosely following the audio's actual onsets — both are real
# librosa parameters, tuned per-track rather than left at their
# library defaults.
tempo, beat_frames = librosa.beat.beat_track(
    y=y, sr=sr, start_bpm=(min_bpm + max_bpm) / 2.0, tightness=tightness)
tempo = float(np.ravel(tempo)[0])
if not np.isfinite(tempo) or tempo <= 0:
    tempo = 120.0

# Octave-fold the estimate into the user's specified BPM range —
# beat trackers routinely lock onto half or double the true tempo, and
# a plausible range for the material corrects that automatically.
for _ in range(6):
    if tempo >= min_bpm:
        break
    tempo *= 2
for _ in range(6):
    if tempo <= max_bpm:
        break
    tempo /= 2

tempo *= tempo_mult
print(f"TEMPO:{tempo:.1f}")

# --- Key -------------------------------------------------------------
# Krumhansl-Schmuckler key-finding: correlate the track's pitch-class
# profile (chroma, summed over time) against every rotation of the
# major/minor key profiles and keep the best-correlated one.
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F",
                  "F#", "G", "G#", "A", "A#", "B"]
MAJOR_PROFILE = np.array([
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
])
MINOR_PROFILE = np.array([
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
])

chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
profile = chroma.mean(axis=1)
profile = profile - profile.mean()


def _best_rotation(template):
    template = template - template.mean()
    best_i, best_score = 0, -np.inf
    for i in range(12):
        rotated = np.roll(template, i)
        denom = np.linalg.norm(profile) * np.linalg.norm(rotated)
        score = float(np.dot(profile, rotated) / denom) if denom else -np.inf
        if score > best_score:
            best_i, best_score = i, score
    return best_i, best_score


maj_i, maj_score = _best_rotation(MAJOR_PROFILE)
min_i, min_score = _best_rotation(MINOR_PROFILE)
if maj_score >= min_score:
    key_root, key_mode = PITCH_CLASSES[maj_i], "major"
else:
    key_root, key_mode = PITCH_CLASSES[min_i], "minor"
print(f"KEY:{key_root} {key_mode}")

# --- Time signature (heuristic) ---------------------------------------
# True time-signature detection is an open research problem — this is
# a best-effort estimate, not a guarantee. For each candidate beat
# count per bar, it checks how much stronger the onset envelope is on
# the implied downbeat than on the bar's other beats (real downbeats
# tend to be accented); the candidate with the clearest accent pattern
# wins. Falls back to 4/4 — by far the most common signature — on a
# tie or when there aren't enough beats to judge.
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
beat_idx = np.clip(beat_frames, 0, len(onset_env) - 1)
beat_strengths = onset_env[beat_idx]

TIME_SIGNATURES = {2: "2/4", 3: "3/4", 4: "4/4", 5: "5/4", 6: "6/8"}
beats_per_bar, best_contrast = 4, -np.inf
if len(beat_strengths) >= 8:
    for n in TIME_SIGNATURES:
        if len(beat_strengths) < n * 2:
            continue
        groups = [beat_strengths[i::n] for i in range(n)]
        means = [g.mean() for g in groups if len(g)]
        if len(means) < n:
            continue
        contrast = max(means) - (sum(means) / len(means))
        if contrast > best_contrast:
            beats_per_bar, best_contrast = n, contrast
time_sig = TIME_SIGNATURES[beats_per_bar]
print(f"TIMESIG:{time_sig}")

if want_click and click_out:
    # A perfectly even grid at the single detected tempo — not the
    # raw beat_frames — so the metronome holds one steady tempo
    # throughout instead of skipping or drifting with the detector's
    # local corrections.
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    start = float(beat_times[0]) if len(beat_times) else 0.0
    interval = 60.0 / tempo
    duration = len(y) / sr
    n_clicks = max(0, int((duration - start) / interval) + 1)
    click_times = start + np.arange(n_clicks) * interval

    if no_accents:
        # A flat metronome — every click identical, no downbeat
        # emphasis.
        clicks = librosa.clicks(
            times=click_times, sr=sr, click_freq=1000.0,
            click_duration=0.08, length=len(y))
    else:
        # Accent the downbeat of each bar (per the detected time
        # signature) with a higher-pitched click, same as a real
        # metronome/DAW does.
        downbeat_times = click_times[0::beats_per_bar]
        weak_mask = np.ones(len(click_times), dtype=bool)
        weak_mask[0::beats_per_bar] = False
        weak_times = click_times[weak_mask]

        accent = librosa.clicks(
            times=downbeat_times, sr=sr, click_freq=1600.0,
            click_duration=0.08, length=len(y))
        regular = (
            librosa.clicks(
                times=weak_times, sr=sr, click_freq=1000.0,
                click_duration=0.08, length=len(y))
            if len(weak_times) else np.zeros(len(y), dtype=np.float32)
        )
        clicks = accent + regular
    peak = np.max(np.abs(clicks)) if len(clicks) else 0.0
    if peak > 1.0:
        clicks = clicks / peak
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

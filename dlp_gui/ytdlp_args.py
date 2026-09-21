"""Translate UI state into yt-dlp CLI arguments."""
import os

from .constants import AUDIO_QUALITIES, FORMAT_TYPES, VIDEO_QUALITIES


def build_args(fmt_key, qual_key, dest, url, settings):
    fmt_type = FORMAT_TYPES[fmt_key]
    args = []

    if fmt_type == "audio":
        brate = AUDIO_QUALITIES[qual_key]
        afmt = {
            "MP3": "mp3", "M4A": "m4a", "AAC": "aac",
            "FLAC": "flac", "WAV": "wav", "OPUS": "opus", "OGG": "vorbis",
        }.get(fmt_key, "mp3")
        args += [
            "-f", "bestaudio", "-x", "--audio-format", afmt,
            "--audio-quality", brate,
        ]
    else:
        q = VIDEO_QUALITIES[qual_key]
        if fmt_key == "Best Quality (auto)":
            args += ["-f", "bestvideo+bestaudio/best"]
        elif fmt_key == "MP4":
            if q:
                args += [
                    "-f",
                    f"bestvideo{q}[ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo{q}+bestaudio/best{q}",
                ]
            else:
                args += [
                    "-f",
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo+bestaudio/best",
                ]
            args += ["--merge-output-format", "mp4"]
        elif fmt_key == "MKV":
            if q:
                args += ["-f", f"bestvideo{q}+bestaudio/best{q}"]
            else:
                args += ["-f", "bestvideo+bestaudio/best"]
            args += ["--merge-output-format", "mkv"]
        elif fmt_key == "WebM":
            if q:
                args += [
                    "-f",
                    f"bestvideo{q}[ext=webm]+bestaudio[ext=webm]/best{q}",
                ]
            else:
                args += [
                    "-f", "bestvideo[ext=webm]+bestaudio[ext=webm]/best",
                ]
        else:
            args += ["-f", "bestvideo+bestaudio/best"]

    if settings["embed_thumbnail"]:
        args.append("--embed-thumbnail")
    if settings["embed_metadata"]:
        args.append("--embed-metadata")
    if settings["embed_chapters"]:
        args.append("--embed-chapters")
    if settings["sponsorblock"]:
        args += ["--sponsorblock-remove", "all"]

    remux = settings["remux_to"]
    if remux and remux != "None":
        args += ["--remux-video", remux.lower()]

    if settings["write_subs"]:
        args.append("--write-subs")
        if settings["sub_langs"]:
            args += ["--sub-langs", settings["sub_langs"]]
    if settings["write_auto_subs"]:
        args.append("--write-auto-subs")

    if settings["rate_limit"]:
        args += ["--limit-rate", settings["rate_limit"]]
    if settings["concurrent_frags"] > 1:
        args += ["-N", str(settings["concurrent_frags"])]

    cookies = settings["cookies"]
    if cookies and cookies != "None":
        args += ["--cookies-from-browser", cookies.lower()]

    if settings["playlist_mode"] == "single":
        args.append("--no-playlist")
    elif settings["playlist_mode"] == "full":
        args.append("--yes-playlist")

    args += ["-o", os.path.join(dest, settings["out_template"]), url]
    return args

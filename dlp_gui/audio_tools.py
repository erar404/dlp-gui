"""Post-download processing: Spleeter stem splitting, tempo detection,
and click-track generation.
"""
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from .constants import (
    SPLEETER_CHUNK_SECONDS, STEM_INSTRUMENTS, STEM_OPTIONS,
    TEMPO_CLICK_SCRIPT,
)

NUMPY_ABI_HINTS = [
    "_ARRAY_API not found",
    "numpy.core._multiarray_umath failed to import",
]


def _no_window_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _env_with_ffmpeg(ffmpeg_path):
    """Environment with ffmpeg's directory prepended to PATH, and I/O
    forced to UTF-8.

    Spleeter shells out to a bare `ffmpeg` command (via ffmpeg-python)
    instead of taking an explicit binary path like yt-dlp does, so it
    can't find our bundled ffmpeg.exe unless its folder is on PATH.

    Separately, once its stdout is piped (as ours always is) rather
    than a real console, Python falls back to the legacy Windows
    codepage for text output — so Spleeter's own logging (e.g. "File
    <path> written succesfully") crashes with UnicodeEncodeError on
    any non-ASCII filename, such as a title in Thai or another
    non-Latin script. PYTHONIOENCODING/PYTHONUTF8 force UTF-8
    regardless.
    """
    env = os.environ.copy()
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        ffmpeg_dir = os.path.dirname(ffmpeg_path)
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _format_tempo_tag(bpm_value):
    """Render a detected BPM value as a filename-safe tag."""
    try:
        return str(int(round(float(bpm_value))))
    except (TypeError, ValueError):
        return "unknown"


def _spleeter_output_produced(base_dir, instruments):
    """Whether at least one expected stem file actually got written.

    Spleeter can log an internal error (e.g. a missing ffmpeg binary)
    and still exit 0 without producing any output, so a clean exit
    code alone isn't proof the separation worked.
    """
    return any(
        os.path.isfile(os.path.join(base_dir, f"{inst}.wav"))
        for inst in instruments
    )


def _probe_duration_seconds(ffmpeg_path, audio_path):
    """Return the audio's duration in seconds via ffmpeg, or None."""
    try:
        r = subprocess.run(
            [ffmpeg_path, "-i", audio_path],
            capture_output=True, text=True, timeout=30,
            creationflags=_no_window_flags(),
        )
        text = (r.stderr or "") + (r.stdout or "")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if not m:
            return None
        h, mnt, s = m.groups()
        return int(h) * 3600 + int(mnt) * 60 + float(s)
    except Exception:
        return None


class AudioToolsMixin:
    """Adds Spleeter split / tempo / click-track processing to App."""

    def _start_next_split(self):
        if not self._split_queue:
            self._on_split_done()
            return

        audio_file = self._split_queue.pop(0)
        need_analysis = self._tempo_requested or self._click_requested
        no_python = not self.python_path or not os.path.isfile(
            self.python_path)

        if (self._split_requested or need_analysis) and no_python:
            self._log(
                "Audio tools skipped — Python interpreter not set "
                "(Settings → Audio Tools).", "fail",
            )
            self._start_next_split()
            return
        if not os.path.isfile(audio_file):
            self._log(
                f"Audio tools skipped — file not found: {audio_file}",
                "fail",
            )
            self._start_next_split()
            return

        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        dest_dir = os.path.dirname(audio_file)
        results = {}
        self.btn_dl.config(state="disabled", text="Processing audio...")

        def report_abi_hint():
            self._q.put((
                "  Cause: numpy/TensorFlow version conflict in this "
                "Python runtime.", "info",
            ))
            self._q.put((
                "  Fix: Settings → Audio Tools → run ↓ Install Spleeter "
                "(or ⚡ Auto-Setup Audio Tools) again to reinstall a "
                "compatible numpy.", "info",
            ))

        def run_tempo_click():
            if not need_analysis:
                return
            tmp_wav = None
            try:
                self.after(
                    0,
                    lambda: self.btn_dl.config(text="Analyzing tempo..."),
                )
                label = (
                    "Analyzing tempo & generating click track"
                    if self._click_requested else "Analyzing tempo"
                )
                self._q.put((
                    f"{label}: {os.path.basename(audio_file)}", "blue",
                ))

                if self._click_requested:
                    fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
                    os.close(fd)

                cmd = [
                    self.python_path, "-c", TEMPO_CLICK_SCRIPT, audio_file,
                    "1" if self._click_requested else "0", tmp_wav or "",
                ]
                r = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=300,
                    creationflags=_no_window_flags(),
                    env=_env_with_ffmpeg(self.ffmpeg_path),
                )

                abi_mismatch = False
                bpm_value = None
                for line in (r.stdout or "").splitlines():
                    line = line.rstrip()
                    if not line:
                        continue
                    if line.startswith("TEMPO:"):
                        bpm_value = line.split(":", 1)[1].strip()
                    elif not line.startswith("CLICK_WRITTEN:"):
                        self._q.put((line, "gray"))
                for line in (r.stderr or "").splitlines():
                    line = line.rstrip()
                    if not line:
                        continue
                    if any(h in line for h in NUMPY_ABI_HINTS):
                        abi_mismatch = True
                    self._q.put((line, "err"))

                if r.returncode != 0:
                    self._q.put((
                        "Tempo/click analysis failed — exit code "
                        f"{r.returncode}.", "fail",
                    ))
                    if abi_mismatch:
                        report_abi_hint()
                    return

                if bpm_value is not None:
                    self._q.put((
                        f"Suggested tempo: {bpm_value} BPM — "
                        f"{os.path.basename(audio_file)}", "ok",
                    ))
                    self.after(
                        0,
                        lambda b=bpm_value: self.lbl_tempo_result.config(
                            text=f"{b} BPM"),
                    )

                click_ready = (
                    self._click_requested and tmp_wav
                    and os.path.isfile(tmp_wav)
                )
                if click_ready:
                    click_mp3 = os.path.join(
                        dest_dir, f"{base_name}_click.mp3")
                    ffmpeg_cmd = [
                        self.ffmpeg_path, "-y", "-i", tmp_wav,
                        "-codec:a", "libmp3lame", "-qscale:a", "2",
                        click_mp3,
                    ]
                    fr = subprocess.run(
                        ffmpeg_cmd, capture_output=True, text=True,
                        creationflags=_no_window_flags(),
                    )
                    if fr.returncode == 0:
                        self._q.put(
                            (f"Click track saved: {click_mp3}", "ok"))
                        results["click_mp3"] = click_mp3

                        if self._merge_click_requested:
                            tempo_tag = _format_tempo_tag(bpm_value)
                            merged_mp3 = os.path.join(
                                dest_dir,
                                f"{base_name}_with_click_"
                                f"{tempo_tag}.mp3",
                            )
                            merge_cmd = [
                                self.ffmpeg_path, "-y",
                                "-i", audio_file, "-i", click_mp3,
                                "-filter_complex",
                                "amix=inputs=2:duration=longest:"
                                "normalize=0",
                                "-codec:a", "libmp3lame",
                                "-qscale:a", "2", merged_mp3,
                            ]
                            mr = subprocess.run(
                                merge_cmd, capture_output=True,
                                text=True,
                                creationflags=_no_window_flags(),
                            )
                            if mr.returncode == 0:
                                self._q.put((
                                    "Click track merged into audio: "
                                    f"{merged_mp3}", "ok",
                                ))
                                results["merged_mp3"] = merged_mp3
                            else:
                                self._q.put((
                                    "Failed to merge click track into "
                                    "audio — ffmpeg exit code "
                                    f"{mr.returncode}.", "fail",
                                ))
                    else:
                        self._q.put((
                            "Failed to encode click track — ffmpeg exit "
                            f"code {fr.returncode}.", "fail",
                        ))
            except Exception as exc:
                self._q.put((
                    f"Error running tempo/click analysis: {exc}", "err"))
            finally:
                if tmp_wav and os.path.isfile(tmp_wav):
                    try:
                        os.unlink(tmp_wav)
                    except OSError:
                        pass

        def run_one_spleeter_pass(cmd):
            """Run one `spleeter separate` invocation, streaming its
            output into the log. Returns (returncode, abi_mismatch)."""
            env = _env_with_ffmpeg(self.ffmpeg_path)
            if shutil.which("ffmpeg", path=env.get("PATH", "")) is None:
                self._q.put((
                    "Spleeter can't find ffmpeg even with the bundled "
                    "copy on its PATH — check the ffmpeg path in "
                    "Settings → Dependencies.", "err",
                ))
                return 1, False
            self.split_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=_no_window_flags(),
                env=env,
            )
            abi_mismatch = False
            for line in self.split_proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                if any(h in line for h in NUMPY_ABI_HINTS):
                    abi_mismatch = True
                tag = (
                    "err" if ("Error" in line or "Traceback" in line)
                    else "gray"
                )
                self._q.put((line, tag))
            self.split_proc.wait()
            ec = self.split_proc.returncode
            self.split_proc = None
            return ec, abi_mismatch

        def stitch_chunks(work_dir, chunk_dirs, instruments, tracks_dir):
            """Concatenate each instrument's per-chunk WAV files, in
            order, into the final stem files via ffmpeg's concat
            demuxer."""
            os.makedirs(tracks_dir, exist_ok=True)
            for instrument in instruments:
                list_path = os.path.join(
                    work_dir, f"{instrument}_chunks.txt")
                with open(list_path, "w", encoding="utf-8") as f:
                    for cdir in chunk_dirs:
                        wav = os.path.join(
                            cdir, base_name, f"{instrument}.wav")
                        wav = wav.replace("\\", "/").replace("'", "'\\''")
                        f.write(f"file '{wav}'\n")
                out_wav = os.path.join(tracks_dir, f"{instrument}.wav")
                concat_cmd = [
                    self.ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
                    "-i", list_path, "-c", "copy", out_wav,
                ]
                r = subprocess.run(
                    concat_cmd, capture_output=True, text=True,
                    creationflags=_no_window_flags(),
                )
                if r.returncode != 0:
                    self._q.put((
                        f"Failed to stitch '{instrument}' chunks "
                        f"together — ffmpeg exit code {r.returncode}.",
                        "fail",
                    ))
                    return False
            return True

        def run_split():
            if not self._split_requested:
                return
            try:
                stems = STEM_OPTIONS[self.cbo_stems.get()]
                instruments = STEM_INSTRUMENTS[stems]
                tracks_dir = os.path.join(dest_dir, f"{base_name}_tracks")

                self.after(
                    0,
                    lambda: self.btn_dl.config(text="Splitting audio..."),
                )
                self._q.put((
                    f"Splitting with Spleeter ({stems} stems): "
                    f"{os.path.basename(audio_file)}", "blue",
                ))

                duration = _probe_duration_seconds(
                    self.ffmpeg_path, audio_file)

                if not duration or duration <= SPLEETER_CHUNK_SECONDS:
                    cmd = [
                        self.python_path, "-m", "spleeter", "separate",
                        "-p", f"spleeter:{stems}stems",
                        "-f", "{filename}_tracks/{instrument}.{codec}",
                        "-o", dest_dir, audio_file,
                    ]
                    ec, abi_mismatch = run_one_spleeter_pass(cmd)
                    if ec == 0 and not _spleeter_output_produced(
                        tracks_dir, instruments,
                    ):
                        ec = 1
                    if ec == 0:
                        self._q.put((
                            f"Split complete — stems saved to "
                            f"{tracks_dir}", "ok",
                        ))
                    else:
                        self._q.put((
                            f"Spleeter failed — exit code {ec}. See the "
                            "log above for the real error (e.g. a "
                            "missing ffmpeg).", "fail",
                        ))
                        if abi_mismatch:
                            report_abi_hint()
                    return

                # Spleeter (CPU, Windows, this TensorFlow build) crashes
                # natively on long input — process it in chunks instead.
                n_chunks = math.ceil(duration / SPLEETER_CHUNK_SECONDS)
                self._q.put((
                    f"Audio is {duration / 60:.1f} min — Spleeter can "
                    "crash on long input on this system, so it's being "
                    f"processed in {n_chunks} chunks and stitched back "
                    "together.", "info",
                ))
                work_dir = os.path.join(
                    dest_dir, f".{base_name}_spleeter_tmp")
                os.makedirs(work_dir, exist_ok=True)
                chunk_dirs = []
                try:
                    for i in range(n_chunks):
                        offset = i * SPLEETER_CHUNK_SECONDS
                        chunk_out = os.path.join(
                            work_dir, f"chunk_{i:03d}")
                        self._q.put((
                            f"  Chunk {i + 1}/{n_chunks} "
                            f"({offset}s-"
                            f"{offset + SPLEETER_CHUNK_SECONDS}s)...",
                            "gray",
                        ))
                        cmd = [
                            self.python_path, "-m", "spleeter", "separate",
                            "-p", f"spleeter:{stems}stems",
                            "-s", str(offset),
                            "-d", str(SPLEETER_CHUNK_SECONDS),
                            "-o", chunk_out, audio_file,
                        ]
                        ec, abi_mismatch = run_one_spleeter_pass(cmd)
                        if ec == 0 and not _spleeter_output_produced(
                            os.path.join(chunk_out, base_name), instruments,
                        ):
                            ec = 1
                        if ec != 0:
                            self._q.put((
                                f"Spleeter failed on chunk {i + 1}/"
                                f"{n_chunks} — exit code {ec}. See the "
                                "log above for the real error (e.g. a "
                                "missing ffmpeg).", "fail",
                            ))
                            if abi_mismatch:
                                report_abi_hint()
                            return
                        chunk_dirs.append(chunk_out)

                    if stitch_chunks(
                        work_dir, chunk_dirs, instruments, tracks_dir,
                    ):
                        self._q.put((
                            f"Split complete — stems saved to "
                            f"{tracks_dir}", "ok",
                        ))
                finally:
                    shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as exc:
                self._q.put((f"Error launching Spleeter: {exc}", "err"))

        def finalize_outputs():
            """Gather the downloaded audio plus any generated click/
            merged files into one output folder named after the video —
            or, when Spleeter split the audio, into the stems folder it
            already created."""
            tracks_dir = os.path.join(dest_dir, f"{base_name}_tracks")
            split_ok = self._split_requested and os.path.isdir(tracks_dir)
            has_click_outputs = bool(
                results.get("click_mp3") or results.get("merged_mp3"))

            if not split_ok and not has_click_outputs:
                return

            container = (
                tracks_dir if split_ok
                else os.path.join(dest_dir, base_name)
            )
            os.makedirs(container, exist_ok=True)

            for src in (
                audio_file, results.get("click_mp3"),
                results.get("merged_mp3"),
            ):
                if not src or not os.path.isfile(src):
                    continue
                target = os.path.join(container, os.path.basename(src))
                if os.path.abspath(src) == os.path.abspath(target):
                    continue
                try:
                    shutil.move(src, target)
                except OSError as exc:
                    self._q.put((
                        f"Could not move '{os.path.basename(src)}' "
                        f"into output folder: {exc}", "err",
                    ))

            self._q.put((
                f"Output files organized in: {container}", "ok"))

        def run():
            try:
                run_tempo_click()
            except Exception as exc:
                self._q.put((f"Tempo/click step crashed: {exc}", "err"))
            try:
                run_split()
            except Exception as exc:
                self._q.put((f"Split step crashed: {exc}", "err"))
            try:
                finalize_outputs()
            except Exception as exc:
                self._q.put((
                    f"Error organizing output files: {exc}", "err"))
            self._q.put("__SPLIT_DONE__")

        threading.Thread(target=run, daemon=True).start()

    def _on_split_done(self):
        if self._stop_requested:
            self._log("Stopped by user.", "warn")
            self._log("")
            self._stop_requested = False
            self._reset_buttons()
            return
        if self._split_queue:
            self._start_next_split()
            return
        self._log("")
        self._reset_buttons()
        self._show_tip_prompt()

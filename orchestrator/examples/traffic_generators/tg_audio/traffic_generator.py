"""TG-AUDIO: real speech WAV files at a CONSTANT per-job intensity.
"""

import base64
import os
import wave

# Directory containing the .wav files to send. Can be overridden with the
# TG_WAV_PATH environment variable (the name avoids clashing with the system PATH).
PATH = os.environ.get("TG_WAV_PATH", "./wav")

CPU_SCALE = 60  # constant intensity; pair with a short TG interval (~0.4s) so the
# CONCENTRATED node01 saturates by contention (queues -> latency diverges) while the
# DISTRIBUTED placement stays well below the 1.0 s SLA. (calibrated for experiment_2)

_tick = 0
_wav_files: list[str] | None = None
_wav_cache: dict[int, dict] = {}


def _list_wav_files() -> list[str]:
    """Return the sorted list of .wav paths under PATH (resolved once, then cached)."""
    global _wav_files
    if _wav_files is None:
        if not os.path.isdir(PATH):
            raise FileNotFoundError(f"traffic_generator: PATH '{PATH}' is not a directory")
        files = sorted(
            os.path.join(PATH, f)
            for f in os.listdir(PATH)
            if f.lower().endswith(".wav") and os.path.isfile(os.path.join(PATH, f))
        )
        if not files:
            raise FileNotFoundError(f"traffic_generator: no .wav files found in PATH '{PATH}'")
        _wav_files = files
    return _wav_files


def _load_wav(path: str) -> dict:
    """Read a WAV file and return its base64 payload plus header-derived metadata."""
    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
    with open(path, "rb") as fh:
        audio_b64 = base64.b64encode(fh.read()).decode("ascii")
    stem = os.path.splitext(os.path.basename(path))[0]
    phrase = stem.replace("_", " ").replace("-", " ").strip()
    duration_ms = int(round(n_frames * 1000 / sample_rate)) if sample_rate else 0
    return {
        "audio_b64": audio_b64,
        "phrase": phrase,
        "sample_rate": sample_rate,
        "duration_ms": duration_ms,
    }


def traffic_generator():
    global _tick
    _tick += 1
    files = _list_wav_files()
    file_idx = (_tick - 1) % len(files)
    if file_idx not in _wav_cache:
        _wav_cache[file_idx] = _load_wav(files[file_idx])
    wav = _wav_cache[file_idx]
    return {
        "audio_b64": wav["audio_b64"],
        "phrase": wav["phrase"],
        "sample_rate": wav["sample_rate"],
        "duration_ms": wav["duration_ms"],
        "cpu_scale": CPU_SCALE,
        "profile": "audio",
        "tick": _tick,
    }
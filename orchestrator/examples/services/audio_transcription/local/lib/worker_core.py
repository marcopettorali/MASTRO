"""Core logic for audio_transcription (c2ct audio pipeline, MOSAIC local port).

Converts a base-64 encoded WAV audio file to text. Two backends:

* **Vosk** (real offline STT) — used when the ``vosk`` package is importable
  and a model is present at ``VOSK_MODEL_PATH``.
* **Deterministic fallback** — used otherwise. Decodes the WAV and runs an
  energy/zero-crossing analysis whose cost scales with the audio length
  (realistic CPU load for the experiments), then returns the phrase carried
  in the payload as ``transcribed_text``.

Either way the output schema is identical, so the downstream intent
classifier is agnostic to the backend actually used.
"""

import base64
import io
import json
import os
import struct
import wave
from typing import Any

_TARGET_RATE = 16000
_CHUNK_SAMPLES = 4000
_CHUNK_BYTES = _CHUNK_SAMPLES * 2

_DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "model")
MODEL_PATH = os.environ.get("VOSK_MODEL_PATH", _DEFAULT_MODEL_PATH)


# ── WAV → PCM helpers ──────────────────────────────────────────────────────────

def _decode_pcm(raw: bytes) -> tuple[list[int], int]:
    with wave.open(io.BytesIO(raw)) as wf:
        sw = wf.getsampwidth()
        n_ch = wf.getnchannels()
        rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())

    if sw == 2:
        n = len(pcm) // 2
        samples = list(struct.unpack(f"<{n}h", pcm))
    elif sw == 1:
        samples = [(b - 128) * 256 for b in pcm]
    elif sw == 4:
        n = len(pcm) // 4
        samples = [s >> 16 for s in struct.unpack(f"<{n}i", pcm)]
    else:
        raise ValueError(f"Unsupported sample width: {sw}")

    if n_ch > 1:
        mono: list[int] = []
        for i in range(0, len(samples), n_ch):
            chunk = samples[i:i + n_ch]
            mono.append(int(sum(chunk) / len(chunk)))
        samples = mono
    return samples, rate


def _pcm_bytes_16k(samples: list[int], src_rate: int) -> bytes:
    if src_rate != _TARGET_RATE and samples:
        ratio = src_rate / _TARGET_RATE
        resampled: list[int] = []
        i = 0.0
        while int(i) < len(samples):
            resampled.append(samples[int(i)])
            i += ratio
        samples = resampled
    return struct.pack(f"<{len(samples)}h", *samples)


# ── Backend: real Vosk ─────────────────────────────────────────────────────────

def _transcribe_vosk(raw: bytes) -> tuple[str, float] | None:
    try:
        from vosk import Model, KaldiRecognizer  # noqa: PLC0415
    except ImportError:
        return None
    if not os.path.isdir(MODEL_PATH):
        return None

    samples, rate = _decode_pcm(raw)
    pcm = _pcm_bytes_16k(samples, rate)
    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, _TARGET_RATE)
    rec.SetWords(True)
    for i in range(0, len(pcm), _CHUNK_BYTES):
        rec.AcceptWaveform(pcm[i:i + _CHUNK_BYTES])
    final = json.loads(rec.FinalResult())
    text = final.get("text", "").strip()
    words = final.get("result", [])
    conf = round(sum(w.get("conf", 0.0) for w in words) / len(words), 4) if words else 0.0
    return text, conf


# ── Backend: deterministic CPU-bound fallback ──────────────────────────────────

def _transcribe_fallback(raw: bytes, payload: dict) -> tuple[str, float]:
    """Length-proportional signal analysis; returns the payload phrase as text.

    The analysis (framewise energy + zero-crossing rate) is pure-Python and
    O(n) in the number of samples, so the CPU cost tracks the audio duration
    just like a real recogniser would. The optional ``cpu_scale`` (int,
    default 1) repeats the analysis to raise the per-job CPU cost — the load
    ramp uses it to drive a node into saturation deterministically.
    """
    samples, _rate = _decode_pcm(raw)
    try:
        cpu_scale = max(1, int(payload.get("cpu_scale", 1)))
    except (TypeError, ValueError):
        cpu_scale = 1

    frame = 320
    n_frames = max(1, len(samples) // frame)
    energy_acc = 0.0
    zcr_acc = 0
    for _ in range(cpu_scale):
        energy_acc = 0.0
        zcr_acc = 0
        for i in range(n_frames):
            seg = samples[i * frame:(i + 1) * frame]
            energy_acc += sum(s * s for s in seg)
            prev = seg[0] if seg else 0
            for s in seg[1:]:
                if (s >= 0) != (prev >= 0):
                    zcr_acc += 1
                prev = s
    # Pseudo-confidence derived from the (discarded) analysis, kept realistic.
    mean_energy = energy_acc / max(1, len(samples))
    conf = round(min(1.0, mean_energy / 1e8 + 0.5), 4)

    text = str(payload.get("phrase", payload.get("transcribed_text", ""))).strip()
    return text, conf


# ── Public API ─────────────────────────────────────────────────────────────────

def transcribe(payload: dict) -> dict:
    """Perform offline speech-to-text on the audio in *payload*.

    Returns all original keys plus ``transcribed_text``,
    ``transcription_confidence`` and ``transcription_backend``.
    ``audio_b64`` is dropped (downstream stages do not need it).
    """
    result: dict[str, Any] = dict(payload)
    audio_b64: str = payload.get("audio_b64", "")

    text, conf, backend = "", 0.0, "none"
    if audio_b64:
        raw = base64.b64decode(audio_b64)
        vosk_out = _transcribe_vosk(raw)
        if vosk_out is not None:
            text, conf = vosk_out
            backend = "vosk"
        else:
            text, conf = _transcribe_fallback(raw, payload)
            backend = "fallback"

    result.update({
        "transcribed_text": text,
        "transcription_confidence": conf,
        "transcription_backend": backend,
    })
    result.pop("audio_b64", None)
    return result

"""Core logic for audio_noise_removal (c2ct audio pipeline, MOSAIC local port).

Applies a Wiener-style noise suppression filter to the incoming audio to
reduce the background noise added at the traffic-generator stage. Pure Python
+ stdlib: the per-sample work makes CPU cost scale with the audio duration,
which is what drives node saturation in the rebalancing experiments.

Noise reduction pipeline
------------------------
1. Decode the base-64 audio payload into 16-bit PCM samples.
2. Divide the signal into short frames (20 ms at 16 kHz).
3. Estimate the noise floor from the energy of the quietest frames.
4. Apply a per-frame Wiener gain: G = max(0, 1 - noise_floor / frame_energy).
5. Re-encode the denoised audio as a WAV and produce a new ``audio_b64``.
"""

import base64
import io
import struct
import wave
from typing import Any

# ── Tuning parameters ────────────────────────────────────────────────────────
_FRAME_SIZE = 320        # 20 ms at 16 kHz (16-bit samples)
_NOISE_PERCENTILE = 0.2  # fraction of quietest frames used to estimate noise floor


# ── WAV encode / decode helpers ───────────────────────────────────────────────

def _decode_wav_pcm(raw_wav: bytes) -> tuple[list[int], int]:
    """Decode a WAV file into 16-bit PCM samples and the sample rate."""
    with wave.open(io.BytesIO(raw_wav)) as wf:
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


def _encode_wav_pcm(samples: list[int], rate: int) -> bytes:
    """Encode 16-bit mono PCM samples into a WAV file (bytes)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


# ── Noise reduction ────────────────────────────────────────────────────────────

def _reduce_noise(signal: list[int],
                  frame_size: int = _FRAME_SIZE,
                  noise_percentile: float = _NOISE_PERCENTILE) -> list[int]:
    """Apply a Wiener-style spectral noise suppression to *signal*."""
    if not signal:
        return signal

    n_frames = len(signal) // frame_size
    if n_frames < 2:
        return signal

    energies: list[float] = []
    for i in range(n_frames):
        frame = signal[i * frame_size: (i + 1) * frame_size]
        energy = sum(s * s for s in frame) / frame_size
        energies.append(energy)

    sorted_e = sorted(energies)
    n_noise = max(1, int(len(sorted_e) * noise_percentile))
    noise_floor = sum(sorted_e[:n_noise]) / n_noise
    if noise_floor == 0.0:
        return signal

    result = list(signal)
    for i in range(n_frames):
        fe = energies[i]
        if fe > 0:
            gain = max(0.0, 1.0 - noise_floor / fe)
            base = i * frame_size
            for j in range(frame_size):
                result[base + j] = int(signal[base + j] * gain)

    return result


# ── Core service function ──────────────────────────────────────────────────────

def remove_background_noise(payload: dict) -> dict:
    """Apply noise reduction to the audio in *payload*.

    Parameters
    ----------
    payload:
        Must contain ``audio_b64`` (base-64 WAV). All other keys are forwarded.
        Optional ``cpu_scale`` (int, default 1) repeats the denoise pass to
        raise the per-job CPU cost without changing the audio size — used as a
        load-control knob in the rebalancing experiments.

    Returns
    -------
    dict
        All original keys with ``audio_b64`` replaced by the denoised version,
        plus ``denoised`` (bool).
    """
    result: dict[str, Any] = dict(payload)

    audio_b64: str = payload.get("audio_b64", "")
    try:
        cpu_scale = max(1, int(payload.get("cpu_scale", 1)))
    except (TypeError, ValueError):
        cpu_scale = 1

    denoised = False
    if audio_b64:
        raw_wav = base64.b64decode(audio_b64)
        signal, rate = _decode_wav_pcm(raw_wav)
        if signal:
            cleaned = signal
            for _ in range(cpu_scale):
                cleaned = _reduce_noise(cleaned)
            denoised_wav = _encode_wav_pcm(cleaned, rate)
            result["audio_b64"] = base64.b64encode(denoised_wav).decode("ascii")
            denoised = True

    result["denoised"] = denoised
    return result

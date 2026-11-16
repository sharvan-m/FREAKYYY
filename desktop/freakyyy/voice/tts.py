"""Freakyyy's voice on Windows: Kokoro-82M, am_onyx, 1.08x, Freakyyy sound profile.

Primary engine : kokoro-onnx (model_quantized.onnx + am_onyx) - multi-threaded,
                 ~0.4x real time on a laptop CPU.
Fallback engine: MediaPipe TextToSpeech with the same kokoro_int8_fp16.litertlm
                 bundle the phone uses (slower on this CPU, same voice).
There is no fallback to Windows SAPI voices: if Kokoro can't load, Freakyyy
shows VOICE OFFLINE instead of speaking with a different identity.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections import OrderedDict
from typing import Callable

import numpy as np
import sounddevice as sd

from ..config import models_dir, settings
from .audio_dsp import FreakyyyAudioProcessor

log = logging.getLogger(__name__)
SR = 24_000


class _OnnxKokoro:
    name = "Kokoro-82M (ONNX q8)"

    def __init__(self) -> None:
        from kokoro_onnx import Kokoro
        m = models_dir()
        self.k = Kokoro(str(m / "model_quantized.onnx"), str(m / "voices-am_onyx.bin"))

    def synth(self, text: str, voice: str, speed: float) -> np.ndarray:
        audio, sr = self.k.create(text, voice=voice, speed=speed, lang="en-us")
        if sr != SR:
            from scipy.signal import resample_poly
            audio = resample_poly(audio, SR, sr)
        return audio.astype(np.float32)


class _LiteRtKokoro:
    name = "Kokoro-82M (LiteRT-LM int8)"

    def __init__(self, voice: str, speed: float) -> None:
        from mediapipe.tasks.python.audio import text_to_speech as tts
        from mediapipe.tasks.python.core.base_options import BaseOptions
        m = models_dir()
        opts = tts.TextToSpeechOptions(
            base_options=BaseOptions(model_asset_path=str(m / "kokoro_int8_fp16.litertlm")),
            default_voice_id=voice, speaking_rate=speed, cache_dir=str(m / ".cache"))
        self.engine = tts.TextToSpeech.create_from_options(opts)

    def synth(self, text: str, voice: str, speed: float) -> np.ndarray:
        chunks = [c.samples for c in self.engine.synthesize_stream(text)]
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    out: list[str] = []
    for p in parts:
        while len(p) > 240:                      # keep chunks short for low latency
            cut = p.rfind(", ", 0, 240)
            cut = cut + 1 if cut > 60 else 240
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out


class FreakyyyVoice:
    """Load once, speak many times. `speak()` replaces current speech."""

    def __init__(self, on_state: Callable[[str], None] | None = None,
                 on_level: Callable[[float], None] | None = None) -> None:
        self.on_state = on_state or (lambda s: None)
        self.on_level = on_level or (lambda v: None)
        self.engine = None
        self.status = "loading"
        self.error = ""
        self._jobs: queue.Queue = queue.Queue()
        self._generation = 0
        self._speaking = threading.Event()
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.last_spoken = ""
        threading.Thread(target=self._worker, daemon=True, name="freakyyy-voice").start()

    # ------------------------------------------------------------------
    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    def speak(self, text: str) -> None:
        text = re.sub(r"freakyyy", "Freaky", (text or "").strip(), flags=re.I)
        if not text or not settings.get("voice_enabled"):
            return
        self.last_spoken = text
        self._generation += 1
        sd.stop()
        self._jobs.put((self._generation, text[:2000]))

    def stop(self) -> None:
        self._generation += 1
        sd.stop()

    def wait_idle(self, timeout: float = 30) -> None:
        end = time.time() + timeout
        while (self.speaking or not self._jobs.empty()) and time.time() < end:
            time.sleep(0.05)

    # ------------------------------------------------------------------
    def _load(self) -> None:
        voice, speed = settings.get("voice_id"), float(settings.get("voice_speed"))
        errors = []
        for factory in (lambda: _OnnxKokoro(), lambda: _LiteRtKokoro(voice, speed)):
            try:
                t = time.time()
                self.engine = factory()
                self.engine.synth("Ready.", voice, speed)          # warm-up
                log.info("Voice engine %s ready in %.1fs", self.engine.name, time.time() - t)
                self.status = "ready"
                self.on_state("ready")
                return
            except Exception as e:
                log.exception("Voice engine failed")
                errors.append(str(e))
        self.status = "offline"
        self.error = "; ".join(errors)
        self.on_state("offline")

    def _worker(self) -> None:
        self._load()
        while True:
            gen, text = self._jobs.get()
            if gen != self._generation or self.engine is None:
                continue
            self._speaking.set()
            self.on_state("speaking")
            try:
                self._speak_now(gen, text)
            except Exception:
                log.exception("Speech failed")
            finally:
                if self._jobs.empty():
                    self._speaking.clear()
                    self.on_level(0.0)
                    self.on_state("ready")

    def _speak_now(self, gen: int, text: str) -> None:
        voice, speed = settings.get("voice_id"), float(settings.get("voice_speed"))
        dsp = FreakyyyAudioProcessor(SR)
        pending: queue.Queue = queue.Queue()

        def produce():
            for sentence in split_sentences(text):
                if gen != self._generation:
                    break
                clip = self._cache.get(sentence)
                if clip is None:
                    raw = self.engine.synth(sentence, voice, speed)
                    clip = dsp.process(raw)
                    if len(sentence) <= 60:
                        self._cache[sentence] = clip
                        while len(self._cache) > 64:
                            self._cache.popitem(last=False)
                pending.put(clip)
            pending.put(None)

        threading.Thread(target=produce, daemon=True).start()
        with sd.OutputStream(samplerate=SR, channels=1, dtype="float32", blocksize=1200) as out:
            while True:
                clip = pending.get()
                if clip is None or gen != self._generation:
                    break
                for i in range(0, len(clip), 1200):
                    if gen != self._generation:
                        return
                    block = clip[i:i + 1200]
                    self.on_level(float(np.sqrt(np.mean(block ** 2))) * 4)
                    out.write(block.reshape(-1, 1))
            if gen == self._generation:
                out.write(np.zeros((SR // 10, 1), np.float32))     # let the tail play out

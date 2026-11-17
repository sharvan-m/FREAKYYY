"""Hands-free listening: local wake word -> command capture -> local speech-to-text.

    WAKE (Vosk, tiny grammar, ~1-2% CPU)
      -> "freakyyy" heard -> WAKE_DETECTED (1.2 s pre-roll kept, so
         "Hey Freaky, open Chrome" in one breath works)
      -> LISTENING (energy VAD with adaptive noise floor, endpoint on silence)
      -> RECOGNIZING (faster-whisper base.en, int8, on CPU)
      -> callback(text) -> back to WAKE (or a short follow-up window)

Audio never leaves the computer and is never written to disk.
"""
from __future__ import annotations

import collections
import json
import logging
import queue
import re
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from ..config import models_dir, settings

log = logging.getLogger(__name__)
RATE = 16_000
BLOCK = 1_600                     # 100 ms

_WAKE_TOKENS = re.compile(r"\b(hey|hi|okay|ok|yo|wake up|wakeup)?[,]?\s*(freaky+|freakie|freakey|freaki|freeky|freaky's|frikki|friki)\b[,.!]?", re.I)


_NAME = r"(freak(y+|ie|ey|i)|freeky|frikki|friki)('s)?"
# Stage 1 (Vosk, every 100 ms): only the whole phrase counts - "freaky" on its own in a chat never does.
_STAGE1 = re.compile(r"\b(hey|hi|hello|okay|ok|wake up) freaky\b")
# Stage 2 (Whisper, accurate): the utterance must START with the greeting + name.
# Includes how Whisper mishears a quick "hey" (hay, helly, howie, hei, hai) - but never "how"/"so"/"that".
_GREET = r"(hey|heyy|hi|hay|hai|hei|hello|helly|howie|okay|ok|wake up)"
_VERIFY = re.compile(r"^\W*" + _GREET + r"\W+" + _NAME + r"\b", re.I)
_VERIFY_LOOSE = re.compile(r"^\W*(" + _GREET + r"\W+)?" + _NAME + r"\b", re.I)


def stage1_hit(vosk_text: str) -> bool:
    return bool(_STAGE1.search(vosk_text))


def verified_wake(whisper_text: str, sensitivity: str = "normal") -> bool:
    """Accept only 'Hey Freaky ...' at the start ('Freaky ...' alone too in sensitive mode)."""
    return bool((_VERIFY_LOOSE if sensitivity == "sensitive" else _VERIFY).match(whisper_text.strip()))


def strip_wake(text: str) -> tuple[str, bool]:
    m = _WAKE_TOKENS.search(text)
    if not m or m.start() > 12:            # wake word must lead the utterance
        return text.strip(), False
    rest = (text[:m.start()] + text[m.end():]).strip(" ,.!?")
    return rest, True


class Listener:
    def __init__(self, on_command: Callable[[str], None], on_state: Callable[[str], None],
                 on_level: Callable[[float], None], is_speaking: Callable[[], bool],
                 on_partial: Callable[[str], None] | None = None) -> None:
        self.on_command = on_command
        self.on_partial = on_partial or (lambda t: None)
        self._cancel = threading.Event()
        self.on_state = on_state
        self.on_level = on_level
        self.is_speaking = is_speaking
        self.enabled = bool(settings.get("wake_enabled"))
        self.mic_active = False
        self.error = ""
        self._audio: queue.Queue = queue.Queue(maxsize=200)
        self._force_capture = threading.Event()
        self._follow_up_seconds = 0.0
        self._stream = None
        self._stop = threading.Event()
        self._restart = threading.Event()
        self.ready = False
        threading.Thread(target=self._run, daemon=True, name="freakyyy-listener").start()

    # ---------------------------------------------------------------- control
    def push_to_talk(self) -> None:
        self._force_capture.set()

    def cancel(self) -> None:
        """Abandon the command being captured (Cancel button / Esc)."""
        self._cancel.set()

    def expect_reply(self, seconds: float | None = None) -> None:
        """Listen without the wake word once Freakyyy finishes speaking."""
        self._follow_up_seconds = seconds or float(settings.get("follow_up_seconds"))

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        settings.set("wake_enabled", enabled)
        self._restart.set()

    def change_device(self) -> None:
        self._restart.set()

    @staticmethod
    def input_devices() -> list[tuple[int, str]]:
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["hostapi"] == 0:
                out.append((i, d["name"]))
        return out

    # ---------------------------------------------------------------- engine
    def _load(self):
        import vosk
        from faster_whisper import WhisperModel
        vosk.SetLogLevel(-1)
        m = models_dir()
        self._vosk_model = vosk.Model(str(m / "vosk-model-small-en-us-0.15"))
        self._whisper = WhisperModel(str(m / f"whisper-{settings.get('stt_model')}"), device="cpu",
                                     compute_type="int8", cpu_threads=4)
        # Decoys keep similar phrases ("hey jarvis", "freak", "free") from being forced onto "freaky".
        # Only whole wake phrases are listed; the many decoys soak up everyday speech that sounds close
        # ("that's freaky", "hey pretty", "are you free", "sneaky"...) so it isn't forced onto the wake phrase.
        self._grammar = json.dumps(["hey freaky", "okay freaky", "hi freaky", "hello freaky", "wake up freaky",
                                    "freaky", "freak", "freaking", "free", "freedom", "pretty", "frankly", "frequently",
                                    "sneaky", "cheeky", "creepy", "squeaky", "tricky", "frisky", "geeky", "leaky",
                                    "really", "very", "ready", "freddie", "frank", "hey frank", "hey there", "hey guys",
                                    "hey bro", "hey buddy", "hey man", "hey jarvis", "hey siri", "alexa", "okay google",
                                    "okay", "hey", "hi", "hello", "[unk]"])

    def _new_recognizer(self):
        import vosk
        return vosk.KaldiRecognizer(self._vosk_model, RATE, self._grammar)

    def _open_stream(self):
        def cb(indata, frames, t, status):
            try:
                self._audio.put_nowait(bytes(indata))
            except queue.Full:
                pass
        device = settings.get("mic_device")
        self._stream = sd.RawInputStream(samplerate=RATE, blocksize=BLOCK, dtype="int16", channels=1,
                                         device=device, callback=cb)
        self._stream.start()
        self.mic_active = True

    def _close_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self.mic_active = False

    def _run(self) -> None:
        try:
            self._load()
        except Exception as e:
            log.exception("Speech models failed to load")
            self.error = f"Speech models failed to load: {e}"
            self.on_state("ERROR")
            return
        self.ready = True
        while not self._stop.is_set():
            self._restart.clear()
            try:
                # The mic is only opened while listening is enabled, or for push-to-talk.
                if not self.enabled:
                    self._close_stream()
                    self.on_state("IDLE")
                    while not (self._restart.is_set() or self._force_capture.is_set()):
                        time.sleep(0.1)
                    if self._force_capture.is_set():
                        self._open_stream()
                        self._force_capture.clear()
                        self._capture_and_recognize(require_wake=False, preroll=b"")
                        self._close_stream()
                    continue
                self._open_stream()
                self.error = ""
                self._wake_loop()
            except Exception as e:
                log.exception("Microphone error")
                self.error = f"Microphone error: {e}"
                self.on_state("ERROR")
                self._close_stream()
                time.sleep(3)          # recover after temporary errors (unplugged headset...)
        self._close_stream()

    def _wake_loop(self) -> None:
        rec = self._new_recognizer()
        ring: collections.deque = collections.deque(maxlen=20)       # 2 s pre-roll (holds "Hey Freaky")
        self.on_state("IDLE")
        sensitivity = settings.get("wake_sensitivity")
        while not self._restart.is_set():
            try:
                block = self._audio.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.is_speaking() and not self._force_capture.is_set():
                # Don't let Freakyyy wake itself; push-to-talk still interrupts.
                ring.clear()
                rec = self._new_recognizer()
                continue
            ring.append(block)

            if self._force_capture.is_set():
                self._force_capture.clear()
                self._drain()
                self._capture_and_recognize(require_wake=False, preroll=b"")
                rec = self._new_recognizer()
                ring.clear()
                continue

            if self._follow_up_seconds:
                seconds, self._follow_up_seconds = self._follow_up_seconds, 0.0
                self._capture_and_recognize(require_wake=False, preroll=b"", timeout=seconds, follow_up=True)
                rec = self._new_recognizer()
                ring.clear()
                continue

            heard = ""
            if rec.AcceptWaveform(block):
                heard = json.loads(rec.Result()).get("text", "")
            elif sensitivity != "strict":
                heard = json.loads(rec.PartialResult()).get("partial", "")
            if stage1_hit(heard):
                # Possible wake: record quietly and check with Whisper BEFORE showing or chiming anything,
                # so a friend saying something similar never wakes Freakyyy.
                self._verify_and_run(b"".join(ring), sensitivity)
                rec = self._new_recognizer()
                ring.clear()

    def _drain(self):
        while not self._audio.empty():
            try:
                self._audio.get_nowait()
            except queue.Empty:
                break

    def _verify_and_run(self, preroll: bytes, sensitivity: str) -> None:
        audio = self._capture(preroll, 4.0, quiet=True)
        if audio is None:
            return
        text = self._transcribe(audio)
        ok = verified_wake(text, sensitivity)
        log.info("Heard: %r (wake=%s)", text, ok)
        if not ok:
            return                                  # stays asleep: no chime, no notch, nothing runs
        self.on_state("WAKE_DETECTED")
        rest, _ = strip_wake(text)
        if not rest:
            self.on_command("")                     # just "Hey Freaky": ask and listen for the command
            return
        self.on_partial(rest)
        self.on_state("RECOGNIZING")
        self.on_command(rest)

    def _capture_and_recognize(self, require_wake: bool, preroll: bytes, timeout: float | None = None,
                               follow_up: bool = False) -> None:
        self.on_state("LISTENING")
        self._cancel.clear()
        audio = self._capture(preroll, timeout or float(settings.get("listen_timeout_seconds")))
        self.on_level(0.0)
        if self._cancel.is_set():
            self._cancel.clear()
            self.on_partial("")
            self.on_state("IDLE")
            return
        if audio is None:
            self.on_state("IDLE")
            return
        self.on_state("RECOGNIZING")
        text = self._transcribe(audio)
        rest, had_wake = strip_wake(text)
        log.info("Heard: %r (wake=%s)", text, had_wake)
        if require_wake and not had_wake:
            self.on_state("IDLE")         # Vosk false alarm (e.g. "hey jarvis")
            return
        if not rest:
            if had_wake or not follow_up:
                # Just "Hey Freaky": ask and listen again without the wake word.
                self.on_command("")
            else:
                self.on_state("IDLE")
            return
        self.on_command(rest)

    def _capture(self, preroll: bytes, timeout: float, quiet: bool = False) -> np.ndarray | None:
        chunks = [preroll] if preroll else []
        start = time.time()
        noise = 250.0
        speech_s = 0.0
        silence_s = 0.0
        heard_speech = bool(preroll) and self._rms(preroll) > 600
        # Live transcript: a full-vocabulary Vosk pass, only while a command is being captured.
        import vosk
        live = None if quiet else vosk.KaldiRecognizer(self._vosk_model, RATE)     # quiet = not woken yet
        if preroll and live:
            live.AcceptWaveform(preroll)
        shown = ""
        while True:
            if self._restart.is_set() or self._cancel.is_set():
                return None
            try:
                block = self._audio.get(timeout=0.5)
            except queue.Empty:
                continue
            chunks.append(block)
            if live is None:
                pass
            elif live.AcceptWaveform(block):
                text = json.loads(live.Result()).get("text", "")
                shown = (shown + " " + text).strip() if text else shown
                if text:
                    self.on_partial(shown)
            else:
                partial = json.loads(live.PartialResult()).get("partial", "")
                if partial:
                    self.on_partial((shown + " " + partial).strip())
            rms = self._rms(block)
            if not quiet:
                self.on_level(min(1.0, rms / 4000))
            threshold = max(noise * 2.8, 450)
            if rms > threshold:
                speech_s += 0.1
                silence_s = 0
                if speech_s >= 0.2:
                    heard_speech = True
            else:
                noise = noise * 0.9 + rms * 0.1          # adaptive noise floor
                silence_s += 0.1
            elapsed = time.time() - start
            if heard_speech and silence_s >= 0.8:
                break
            if not heard_speech and elapsed > timeout:
                return None
            if elapsed > 15:
                break
        pcm = np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768
        return pcm

    @staticmethod
    def _rms(block: bytes) -> float:
        a = np.frombuffer(block, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a * a))) if len(a) else 0.0

    def _transcribe(self, pcm: np.ndarray) -> str:
        prompt = ("Open VS Code, Android Studio, Chrome, WhatsApp, Gradle, GitHub, "
                  "PowerShell, my phone, the Freaky ecosystem project.")
        segments, _ = self._whisper.transcribe(pcm, language="en", beam_size=1, initial_prompt=prompt,
                                               vad_filter=False, condition_on_previous_text=False)
        return " ".join(s.text for s in segments).strip()

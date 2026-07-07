"""
Offline voice SOS detection using Vosk.

The listener keeps the existing VoiceSOSTrigger contract used by app.py:
- start_listening()
- check_triggered()

It also exposes pop_triggered_event() so the main loop can consume richer
metadata when a voice SOS is confirmed.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

try:
    from fuzzywuzzy import fuzz
except ImportError:  # pragma: no cover - fallback for minimal environments
    fuzz = None

try:
    import pyaudio
except ImportError:  # pragma: no cover - optional when running offline tests
    pyaudio = None

try:
    from vosk import KaldiRecognizer, Model
except ImportError:  # pragma: no cover - optional when running offline tests
    KaldiRecognizer = None
    Model = None

from config import (
    VOICE_CHUNK_SIZE,
    VOICE_CONFIRMATION_HITS,
    VOICE_CONFIRMATION_WINDOW_SECONDS,
    VOICE_ENGINE,
    VOICE_HIGH_CONFIDENCE_THRESHOLD,
    VOICE_MATCH_THRESHOLD,
    VOICE_MODEL_PATH,
    VOICE_MODEL_VERSION,
    VOICE_SAMPLE_RATE,
    VOICE_TRIGGER_COOLDOWN_SECONDS,
    VOICE_TRIGGER_PHRASES,
)


Logger = Callable[[str, str], None]

DEFAULT_VOICE_PHRASES: tuple[str, ...] = (
    "help",
    "help me",
    "please help",
    "save me",
    "i need help",
    "i am in danger",
    "i'm in danger",
    "someone help me",
    "call police",
    "emergency",
    "bachao",
    "madad",
    "mujhe bachao",
    "koi hai",
    "help karo",
)


def _log(logger: Logger | None, message: str, prefix: str = "INFO") -> None:
    if logger is None:
        print(f"[{prefix}] {message}")
        return
    logger(message, prefix)


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _phrase_catalog(extra_phrases: Iterable[str] | None = None) -> tuple[str, ...]:
    catalog: list[str] = list(DEFAULT_VOICE_PHRASES)
    catalog.extend(str(item).strip() for item in (VOICE_TRIGGER_PHRASES or ()) if str(item).strip())
    if extra_phrases:
        catalog.extend(str(item).strip() for item in extra_phrases if str(item).strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for phrase in catalog:
        normalized = _normalize_text(phrase)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(phrase.strip())
    return tuple(deduped)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0

    if fuzz is not None:
        scores = (
            fuzz.ratio(a, b),
            fuzz.partial_ratio(a, b),
            fuzz.token_set_ratio(a, b),
        )
        return max(scores) / 100.0

    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def _word_confidence(result: dict[str, Any]) -> float | None:
    word_results = result.get("result")
    if not isinstance(word_results, list):
        return None

    confidences: list[float] = []
    for word_item in word_results:
        if not isinstance(word_item, dict):
            continue
        value = word_item.get("conf")
        try:
            if value is not None:
                confidences.append(float(value))
        except (TypeError, ValueError):
            continue

    if not confidences:
        return None
    return sum(confidences) / float(len(confidences))


def _safe_json(raw_value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(slots=True)
class VoiceMatch:
    label: str
    transcript: str
    normalized_transcript: str
    matched_phrase: str
    score: float
    confidence: float
    match_kind: str
    source: str
    reason: str
    recognition_confidence: float | None = None


class VoicePhraseMatcher:
    """Score transcripts against a small emergency phrase catalog."""

    def __init__(
        self,
        *,
        phrases: Iterable[str] | None = None,
        label: str = "SOS",
        match_threshold: float = VOICE_MATCH_THRESHOLD,
        high_confidence_threshold: float = VOICE_HIGH_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.label = label
        self.phrases = _phrase_catalog(phrases)
        self.match_threshold = max(0.0, min(1.0, float(match_threshold)))
        self.high_confidence_threshold = max(0.0, min(1.0, float(high_confidence_threshold)))

    def match(
        self,
        transcript: str,
        *,
        source: str = "final",
        recognition_confidence: float | None = None,
    ) -> VoiceMatch | None:
        normalized_transcript = _normalize_text(transcript)
        if not normalized_transcript:
            return None

        best_match: VoiceMatch | None = None
        for phrase in self.phrases:
            normalized_phrase = _normalize_text(phrase)
            if not normalized_phrase:
                continue

            match_kind = ""
            score = 0.0
            if normalized_transcript == normalized_phrase:
                match_kind = "exact"
                score = 1.0
            elif normalized_phrase in normalized_transcript or normalized_transcript in normalized_phrase:
                match_kind = "contains"
                score = 0.98
            else:
                score = _similarity(normalized_transcript, normalized_phrase)
                if score >= self.match_threshold:
                    match_kind = "fuzzy"

            if not match_kind:
                continue

            confidence = float(score)
            if recognition_confidence is not None:
                confidence = max(confidence, float(recognition_confidence))
            if source == "partial":
                confidence = min(confidence, 0.97)
            confidence = max(0.0, min(1.0, confidence))

            reason = f"{match_kind} match for phrase '{phrase}'"
            candidate = VoiceMatch(
                label=self.label,
                transcript=transcript.strip(),
                normalized_transcript=normalized_transcript,
                matched_phrase=phrase.strip(),
                score=float(score),
                confidence=float(confidence),
                match_kind=match_kind,
                source=source,
                reason=reason,
                recognition_confidence=recognition_confidence,
            )

            if best_match is None or candidate.confidence > best_match.confidence:
                best_match = candidate

        return best_match


class VoiceSOSTrigger:
    """Capture microphone audio, transcribe locally, and confirm SOS phrases."""

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        sample_rate: int = VOICE_SAMPLE_RATE,
        chunk_size: int = VOICE_CHUNK_SIZE,
        confirmation_hits: int = VOICE_CONFIRMATION_HITS,
        confirmation_window_seconds: float = VOICE_CONFIRMATION_WINDOW_SECONDS,
        trigger_cooldown_seconds: float = VOICE_TRIGGER_COOLDOWN_SECONDS,
        match_threshold: float = VOICE_MATCH_THRESHOLD,
        high_confidence_threshold: float = VOICE_HIGH_CONFIDENCE_THRESHOLD,
        phrases: Iterable[str] | None = None,
        enable_audio: bool = True,
        logger: Logger | None = None,
    ) -> None:
        self.logger = logger
        self.engine = VOICE_ENGINE
        self.model_path = Path(model_path or VOICE_MODEL_PATH)
        self.model_version = VOICE_MODEL_VERSION
        self.sample_rate = max(8000, int(sample_rate))
        self.chunk_size = max(512, int(chunk_size))
        self.confirmation_hits = max(1, int(confirmation_hits))
        self.confirmation_window_seconds = max(0.5, float(confirmation_window_seconds))
        self.trigger_cooldown_seconds = max(0.0, float(trigger_cooldown_seconds))
        self.match_threshold = max(0.0, min(1.0, float(match_threshold)))
        self.high_confidence_threshold = max(0.0, min(1.0, float(high_confidence_threshold)))
        self.enable_audio = bool(enable_audio and self.engine != "disabled")
        self.matcher = VoicePhraseMatcher(
            phrases=phrases,
            match_threshold=self.match_threshold,
            high_confidence_threshold=self.high_confidence_threshold,
        )

        self.triggered = False
        self.listen_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._state_lock = threading.Lock()
        self._triggered_events: deque[dict[str, Any]] = deque(maxlen=8)
        self._recent_hits: deque[tuple[float, str, VoiceMatch]] = deque()
        self._last_detection: dict[str, Any] | None = None
        self._last_signature: str | None = None
        self._last_signature_at: float = 0.0
        self._cooldown_until: float = 0.0
        self._startup_error: str | None = None
        self._audio_interface = None
        self._audio_stream = None
        self._model = None
        self._last_listener_partial = ""

    def _build_event_id(self, current_time: float) -> str:
        stamp = datetime.fromtimestamp(current_time, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"voice-{stamp}-{uuid4().hex[:8]}"

    def _build_event(self, match: VoiceMatch, current_time: float) -> dict[str, Any]:
        event = {
            "eventId": self._build_event_id(current_time),
            "triggerType": "voice_sos",
            "triggerLabel": "Voice SOS",
            "triggerReason": match.reason,
            "triggerConfidence": round(float(match.confidence), 4),
            "confidence": round(float(match.confidence), 4),
            "voiceConfidence": round(float(match.confidence), 4),
            "voiceTranscript": match.transcript,
            "voiceMatchedPhrase": match.matched_phrase,
            "voiceMatchKind": match.match_kind,
            "voiceSource": match.source,
            "voiceRecognitionConfidence": round(float(match.recognition_confidence), 4)
            if match.recognition_confidence is not None
            else None,
            "voiceEngine": self.engine,
            "voiceModelVersion": self.model_version,
            "voiceModelPath": str(self.model_path),
            "voiceConfirmationHits": len(self._recent_hits),
            "voiceConfirmationWindowSeconds": self.confirmation_window_seconds,
            "voiceCooldownSeconds": self.trigger_cooldown_seconds,
            "frameTime": datetime.fromtimestamp(current_time, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source": "backend_ml",
        }
        return {key: value for key, value in event.items() if value is not None}

    def _register_match(self, match: VoiceMatch, current_time: float) -> dict[str, Any] | None:
        with self._state_lock:
            if current_time < self._cooldown_until:
                self._last_detection = {
                    "transcript": match.transcript,
                    "matchedPhrase": match.matched_phrase,
                    "confidence": round(float(match.confidence), 4),
                    "source": match.source,
                    "cooldown": True,
                }
                return None

            signature = f"{match.label}:{match.normalized_transcript}"
            if signature == self._last_signature and (current_time - self._last_signature_at) < 0.85:
                self._last_detection = {
                    "transcript": match.transcript,
                    "matchedPhrase": match.matched_phrase,
                    "confidence": round(float(match.confidence), 4),
                    "source": match.source,
                    "deduped": True,
                }
                return None

            self._last_signature = signature
            self._last_signature_at = current_time

            self._recent_hits.append((current_time, signature, match))
            while self._recent_hits and (current_time - self._recent_hits[0][0]) > self.confirmation_window_seconds:
                self._recent_hits.popleft()

            confirmation_ready = len(self._recent_hits) >= self.confirmation_hits
            high_confidence_ready = (
                match.confidence >= self.high_confidence_threshold
                and match.match_kind in {"exact", "contains"}
            )

            self._last_detection = {
                "transcript": match.transcript,
                "matchedPhrase": match.matched_phrase,
                "confidence": round(float(match.confidence), 4),
                "source": match.source,
                "windowHits": len(self._recent_hits),
                "windowSeconds": self.confirmation_window_seconds,
                "triggerReady": confirmation_ready or high_confidence_ready,
            }

            if not (confirmation_ready or high_confidence_ready):
                return None

            event = self._build_event(match, current_time)
            self._triggered_events.append(event)
            self.triggered = True
            self._cooldown_until = current_time + self.trigger_cooldown_seconds
            self._recent_hits.clear()
            return event

    def process_transcript(
        self,
        transcript: str,
        *,
        source: str = "final",
        timestamp: float | None = None,
        recognition_confidence: float | None = None,
    ) -> dict[str, Any] | None:
        current_time = float(timestamp if timestamp is not None else time.time())
        match = self.matcher.match(
            transcript,
            source=source,
            recognition_confidence=recognition_confidence,
        )
        if match is None:
            return None
        return self._register_match(match, current_time)

    def _load_runtime(self) -> bool:
        if not self.enable_audio:
            self._startup_error = "Voice listener disabled by configuration"
            self._ready_event.set()
            _log(self.logger, self._startup_error, "WARN")
            return False

        if Model is None or KaldiRecognizer is None:
            self._startup_error = "Vosk is not installed"
            self._ready_event.set()
            _log(self.logger, self._startup_error, "WARN")
            return False

        if pyaudio is None:
            self._startup_error = "PyAudio is not installed"
            self._ready_event.set()
            _log(self.logger, self._startup_error, "WARN")
            return False

        if not self.model_path.exists():
            self._startup_error = f"Voice model not found at {self.model_path}"
            self._ready_event.set()
            _log(
                self.logger,
                "Voice model missing. Download a Vosk model and set VOICE_MODEL_PATH.",
                "WARN",
            )
            _log(self.logger, self._startup_error, "WARN")
            return False

        try:
            self._model = Model(str(self.model_path))
        except Exception as exc:  # pragma: no cover - depends on local model files
            self._startup_error = f"Failed to load voice model: {exc}"
            self._ready_event.set()
            _log(self.logger, self._startup_error, "WARN")
            return False

        self._ready_event.set()
        self._startup_error = None
        _log(self.logger, f"Vosk voice runtime ready from {self.model_path}", "INFO")
        return True

    def _open_audio_stream(self):
        assert pyaudio is not None
        audio_interface = pyaudio.PyAudio()
        stream = audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
        )
        return audio_interface, stream

    def _listen_loop(self) -> None:
        if not self._load_runtime():
            return

        assert self._model is not None
        recognizer = KaldiRecognizer(self._model, self.sample_rate)
        recognizer.SetWords(True)

        try:
            self._audio_interface, self._audio_stream = self._open_audio_stream()
        except Exception as exc:  # pragma: no cover - hardware specific
            self._startup_error = f"Could not open microphone: {exc}"
            _log(self.logger, self._startup_error, "WARN")
            return

        _log(
            self.logger,
            f"Listening for voice SOS using Vosk at {self.sample_rate} Hz",
            "INFO",
        )

        try:
            while not self._stop_event.is_set():
                try:
                    data = self._audio_stream.read(self.chunk_size, exception_on_overflow=False)
                except Exception as exc:  # pragma: no cover - hardware specific
                    _log(self.logger, f"Microphone read error: {exc}", "WARN")
                    time.sleep(0.1)
                    continue

                if not data:
                    continue

                if recognizer.AcceptWaveform(data):
                    result = _safe_json(recognizer.Result())
                    transcript = str(result.get("text", "")).strip()
                    if transcript:
                        confidence = _word_confidence(result)
                        self.process_transcript(
                            transcript,
                            source="final",
                            recognition_confidence=confidence,
                        )
                    continue

                partial = _safe_json(recognizer.PartialResult()).get("partial", "")
                partial = str(partial).strip()
                if not partial or partial == self._last_listener_partial:
                    continue

                self._last_listener_partial = partial
                partial_match = self.matcher.match(partial, source="partial")
                if partial_match is None:
                    continue
                self.process_transcript(
                    partial,
                    source="partial",
                    recognition_confidence=partial_match.recognition_confidence,
                )
        finally:
            try:
                if self._audio_stream is not None:
                    self._audio_stream.stop_stream()
                    self._audio_stream.close()
            except Exception:
                pass

            try:
                if self._audio_interface is not None:
                    self._audio_interface.terminate()
            except Exception:
                pass

            self._audio_stream = None
            self._audio_interface = None

    def start_listening(self) -> bool:
        if self.listen_thread is not None and self.listen_thread.is_alive():
            return self.is_ready()

        if not self.enable_audio:
            _log(self.logger, "Voice listener disabled by configuration", "WARN")
            self._ready_event.set()
            return False

        self._stop_event.clear()
        self._ready_event.clear()
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        self._ready_event.wait(timeout=5.0)
        return self.is_ready()

    def stop_listening(self) -> None:
        self._stop_event.set()

        if self.listen_thread is not None and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_listening()

    def is_ready(self) -> bool:
        return (
            self._ready_event.is_set()
            and self._startup_error is None
            and self._model is not None
            and self._audio_stream is not None
        )

    def get_last_detection(self) -> dict[str, Any] | None:
        with self._state_lock:
            return dict(self._last_detection) if self._last_detection else None

    def pop_triggered_event(self) -> dict[str, Any] | None:
        with self._state_lock:
            if not self._triggered_events:
                self.triggered = False
                return None

            event = self._triggered_events.popleft()
            self.triggered = bool(self._triggered_events)
            return dict(event)

    def check_triggered(self) -> bool:
        return self.pop_triggered_event() is not None

"""Runtime gesture detection for the MediaPipe landmark pipeline."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from time import time
from typing import Any, Iterable

import numpy as np

from config import (
    GESTURE_CONFIRMATION_FRAMES,
    GESTURE_CONFIRMATION_WINDOW,
    GESTURE_ENGINE,
    GESTURE_MIN_CONFIDENCE,
    GESTURE_TRIGGER_LABELS,
)

from .classifier import GestureModelBundle, load_model_bundle
from .features import frame_blur_score, normalize_landmarks, sample_quality_score
from .landmarks import HandLandmarkExtractor, HandObservation
from .registry import resolve_active_model_dir
from .schemas import GestureRuntimeResult


TRIGGER_LABELS = tuple(label.strip().upper() for label in GESTURE_TRIGGER_LABELS if label.strip())

_DEFAULT_RUNTIME: "GestureRuntime | None" = None
_DEFAULT_RUNTIME_LOCK = Lock()


def _normalize_label(label: str | None) -> str:
    return str(label or "").strip().upper()


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _bundle_signature(model_dir: Path | None) -> tuple[str, tuple[float, ...]]:
    if model_dir is None:
        return ("", ())

    files = [
        model_dir / "model.joblib",
        model_dir / "scaler.joblib",
        model_dir / "metadata.json",
        model_dir / "labels.json",
    ]
    mtimes: list[float] = []
    for file_path in files:
        try:
            mtimes.append(float(file_path.stat().st_mtime))
        except FileNotFoundError:
            mtimes.append(0.0)
    return (str(model_dir), tuple(mtimes))


@dataclass(slots=True)
class GestureFrameState:
    label: str
    confidence: float
    raw_confidence: float
    quality_score: float
    hand_present: bool
    frame_score: float


class GestureRuntime:
    """Load the active gesture model and perform temporal confirmation."""

    def __init__(
        self,
        *,
        bundle: GestureModelBundle | None = None,
        extractor: HandLandmarkExtractor | None = None,
        trigger_labels: Iterable[str] | None = None,
        min_confidence: float | None = None,
        confirmation_frames: int | None = None,
        confirmation_window: int | None = None,
        refresh_interval_frames: int = 60,
    ) -> None:
        self.engine = GESTURE_ENGINE
        self.extractor = extractor
        self.trigger_labels = {
            _normalize_label(label)
            for label in (trigger_labels or TRIGGER_LABELS or ("SOS",))
            if _normalize_label(label)
        }
        if not self.trigger_labels:
            self.trigger_labels = {"SOS"}

        self.min_confidence = _clamp_confidence(
            GESTURE_MIN_CONFIDENCE if min_confidence is None else min_confidence
        )
        self.confirmation_frames = max(
            1,
            min(
                int(confirmation_frames or GESTURE_CONFIRMATION_FRAMES),
                int(confirmation_window or GESTURE_CONFIRMATION_WINDOW),
            ),
        )
        self.confirmation_window = max(
            self.confirmation_frames,
            int(confirmation_window or GESTURE_CONFIRMATION_WINDOW),
        )
        self.refresh_interval_frames = max(1, int(refresh_interval_frames))

        self.bundle = bundle
        self._bundle_signature = _bundle_signature(bundle.model_dir if bundle else None)
        self._recent_frames: deque[GestureFrameState] = deque(maxlen=self.confirmation_window)
        self._frame_counter = 0

        if self.bundle is None:
            self.refresh(force=True)

    @property
    def ready(self) -> bool:
        return self.bundle is not None

    @property
    def model_id(self) -> str:
        if self.bundle is None:
            return ""
        return str(self.bundle.model_id)

    @property
    def model_dir(self) -> str:
        if self.bundle is None:
            return ""
        return str(self.bundle.model_dir)

    def close(self) -> None:
        try:
            self.extractor.close()
        except Exception:
            pass
        self._recent_frames.clear()

    def refresh(self, *, force: bool = False) -> bool:
        active_dir = resolve_active_model_dir()
        if active_dir is None:
            if force or self.bundle is not None:
                self.bundle = None
                self._bundle_signature = ("", ())
                self._recent_frames.clear()
            return False

        signature = _bundle_signature(active_dir)
        if not force and self.bundle is not None and signature == self._bundle_signature:
            return True

        try:
            previous_signature = self._bundle_signature
            self.bundle = load_model_bundle(active_dir)
            self._bundle_signature = signature
            if self.extractor is None:
                self.extractor = HandLandmarkExtractor()
            if force or signature != previous_signature:
                self._recent_frames.clear()
            return True
        except Exception:
            self.bundle = None
            self._bundle_signature = ("", ())
            self._recent_frames.clear()
            return False

    def _record_state(self, state: GestureFrameState) -> None:
        self._recent_frames.append(state)

    def _evaluate_confirmation(self) -> tuple[bool, str, float, int, int]:
        valid_frames = [frame for frame in self._recent_frames if frame.hand_present and frame.confidence >= self.min_confidence]
        if not valid_frames:
            return False, "", 0.0, 0, 0

        positive_frames = [
            frame
            for frame in valid_frames
            if _normalize_label(frame.label) in self.trigger_labels
        ]
        if not positive_frames:
            best_frame = max(valid_frames, key=lambda frame: frame.confidence)
            return False, best_frame.label, best_frame.confidence, len(valid_frames), 0

        label_counts = Counter(_normalize_label(frame.label) for frame in positive_frames)
        candidate_label = label_counts.most_common(1)[0][0]
        candidate_frames = [
            frame for frame in positive_frames if _normalize_label(frame.label) == candidate_label
        ]
        average_confidence = float(np.mean([frame.confidence for frame in candidate_frames])) if candidate_frames else 0.0
        positive_count = len(candidate_frames)
        window_count = len(valid_frames)
        confirmed = (
            candidate_label in self.trigger_labels
            and positive_count >= self.confirmation_frames
            and average_confidence >= self.min_confidence
        )
        return confirmed, candidate_label, average_confidence, window_count, positive_count

    def detect(
        self,
        frame: np.ndarray,
        fps: float | None = None,
        observation: HandObservation | None = None,
    ) -> GestureRuntimeResult:
        self._frame_counter += 1
        if self.bundle is None or self._frame_counter % self.refresh_interval_frames == 0:
            self.refresh()

        if self.extractor is None:
            if self.bundle is None:
                return GestureRuntimeResult(
                    hand_present=False,
                    model_ready=False,
                    detected=False,
                    confirmed=False,
                    label=None,
                    confidence=0.0,
                    raw_confidence=0.0,
                    quality_score=0.0,
                    frame_score=0.0,
                    engine=self.engine,
                    classifier="knn",
                    trigger_reason="Gesture runtime unavailable",
                )
            self.extractor = HandLandmarkExtractor()

        frame_score = frame_blur_score(frame)
        observation = observation or self.extractor.extract(frame)
        if observation is None:
            self._recent_frames.clear()
            return GestureRuntimeResult(
                hand_present=False,
                model_ready=self.ready,
                detected=False,
                confirmed=False,
                label=None,
                confidence=0.0,
                raw_confidence=0.0,
                quality_score=0.0,
                frame_score=frame_score,
                engine=self.engine,
                classifier=self.bundle.classifier_name if self.bundle else "knn",
                model_id=self.model_id,
                model_dir=self.model_dir,
                trigger_reason="No hand detected",
            )

        quality_score = sample_quality_score(
            bbox=observation.bbox,
            frame_size=observation.frame_size,
            handedness_score=observation.handedness_score,
            blur_score=frame_score,
        )

        if self.bundle is None:
            self._record_state(
                GestureFrameState(
                    label="",
                    confidence=0.0,
                    raw_confidence=0.0,
                    quality_score=quality_score,
                    hand_present=True,
                    frame_score=frame_score,
                )
            )
            return GestureRuntimeResult(
                hand_present=True,
                model_ready=False,
                detected=False,
                confirmed=False,
                label=None,
                confidence=0.0,
                raw_confidence=0.0,
                quality_score=quality_score,
                frame_score=frame_score,
                handedness=observation.handedness,
                engine=self.engine,
                classifier="knn",
                trigger_reason="Gesture model not loaded",
            )

        features = normalize_landmarks(observation.landmarks, observation.handedness)
        prediction = self.bundle.predict(features)
        raw_confidence = _clamp_confidence(prediction.confidence)
        combined_confidence = _clamp_confidence((0.65 * raw_confidence) + (0.35 * quality_score))

        prediction.confidence = combined_confidence
        self._record_state(
            GestureFrameState(
                label=str(prediction.label or ""),
                confidence=combined_confidence,
                raw_confidence=raw_confidence,
                quality_score=quality_score,
                hand_present=True,
                frame_score=frame_score,
            )
        )

        confirmed, candidate_label, average_confidence, window_count, positive_count = self._evaluate_confirmation()
        trigger_reason = (
            f"{candidate_label or 'gesture'} confirmed in {positive_count}/{window_count} valid frames"
            if confirmed
            else (
                f"{candidate_label or prediction.label or 'gesture'} seen in {positive_count}/{window_count} valid frames"
                if positive_count > 0
                else f"{prediction.label or 'gesture'} below confirmation threshold"
            )
        )

        return GestureRuntimeResult(
            hand_present=True,
            model_ready=True,
            detected=bool(prediction.label),
            confirmed=confirmed,
            label=str(candidate_label or prediction.label or ""),
            confidence=average_confidence if confirmed else combined_confidence,
            raw_confidence=raw_confidence,
            quality_score=quality_score,
            frame_score=frame_score,
            handedness=observation.handedness,
            model_id=self.model_id,
            model_dir=self.model_dir,
            engine=self.bundle.engine,
            classifier=self.bundle.classifier_name,
            trigger_reason=trigger_reason,
            window_count=window_count,
            positive_count=positive_count,
        )


def _get_default_runtime() -> GestureRuntime:
    global _DEFAULT_RUNTIME
    with _DEFAULT_RUNTIME_LOCK:
        if _DEFAULT_RUNTIME is None:
            _DEFAULT_RUNTIME = GestureRuntime()
        return _DEFAULT_RUNTIME


def reload_runtime() -> GestureRuntime:
    global _DEFAULT_RUNTIME
    with _DEFAULT_RUNTIME_LOCK:
        if _DEFAULT_RUNTIME is not None:
            _DEFAULT_RUNTIME.close()
        _DEFAULT_RUNTIME = GestureRuntime()
        return _DEFAULT_RUNTIME


def detect_gesture(
    frame: np.ndarray,
    fps: float | None = None,
    observation: HandObservation | None = None,
) -> GestureRuntimeResult:
    runtime = _get_default_runtime()
    return runtime.detect(frame, fps=fps, observation=observation)


def detect_sos_stable(
    frame: np.ndarray,
    fps: float | None = None,
    observation: HandObservation | None = None,
) -> tuple[bool, float]:
    result = detect_gesture(frame, fps=fps, observation=observation)
    return result.confirmed, result.confidence


def is_runtime_ready() -> bool:
    return _get_default_runtime().ready


def get_runtime_summary() -> dict[str, Any]:
    runtime = _get_default_runtime()
    bundle = runtime.bundle

    summary = {
        "engine": runtime.engine,
        "ready": runtime.ready,
        "triggerLabels": sorted(runtime.trigger_labels),
        "minConfidence": runtime.min_confidence,
        "confirmationFrames": runtime.confirmation_frames,
        "confirmationWindow": runtime.confirmation_window,
    }
    if bundle is not None:
        summary.update(
            {
                "modelId": bundle.model_id,
                "modelDir": str(bundle.model_dir),
                "classifier": bundle.classifier_name,
                "featureVersion": bundle.feature_version,
                "labels": list(bundle.labels),
            }
        )
    return summary


def runtime_state_as_dict(result: GestureRuntimeResult) -> dict[str, Any]:
    return asdict(result)

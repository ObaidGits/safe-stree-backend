#!/usr/bin/env python3
"""Smoke-test the Phase 2 gesture runtime without needing a camera."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from pipelines.hand_gesture.classifier import load_model_bundle, save_model_bundle, train_model_bundle
from pipelines.hand_gesture.landmarks import HandObservation
from pipelines.hand_gesture.runtime import GestureRuntime
from pipelines.hand_gesture.features import normalize_landmarks
from pipelines.hand_gesture.registry import ensure_gesture_storage_layout
from pipelines.hand_gesture.schemas import GesturePrediction, GestureSample


def _make_landmarks(scale: float, bias: float) -> np.ndarray:
    rows = [[0.0, 0.0, 0.0]]
    for index in range(1, 21):
        rows.append([
            (index * 0.04 * scale) + bias,
            (index * 0.02 * scale) + (bias * 0.5),
            index * 0.01 * scale,
        ])
    return np.asarray(rows, dtype=np.float32)


class FakeExtractor:
    def __init__(self, landmarks: np.ndarray) -> None:
        self.landmarks = landmarks

    def extract(self, frame):  # noqa: D401 - test stub
        frame_h, frame_w = frame.shape[:2]
        return HandObservation(
            landmarks=self.landmarks,
            handedness="Right",
            handedness_score=1.0,
            bbox=(12, 16, 120, 160),
            frame_size=(frame_h, frame_w),
            raw_landmarks=None,
        )

    def close(self) -> None:
        return None


class StaticBundle:
    def __init__(self, label: str, confidence: float = 0.95, model_id: str = "static-bundle") -> None:
        self._label = label
        self._confidence = confidence
        self.model_id = model_id
        self.model_dir = Path("/tmp/static-bundle")

    @property
    def classifier_name(self) -> str:
        return "knn"

    @property
    def engine(self) -> str:
        return "mediapipe_landmark"

    @property
    def feature_version(self) -> str:
        return "landmark_63_v1"

    def predict(self, features):  # noqa: D401 - test stub
        return GesturePrediction(
            label=self._label,
            confidence=self._confidence,
            probabilities={self._label: self._confidence},
            feature_version=self.feature_version,
            model_id=self.model_id,
            model_dir=str(self.model_dir),
            engine=self.engine,
            classifier=self.classifier_name,
            hand_present=True,
        )
def main() -> int:
    ensure_gesture_storage_layout()

    sos_landmarks = _make_landmarks(scale=1.0, bias=0.0)
    negative_landmarks = _make_landmarks(scale=-0.8, bias=0.08)

    if normalize_landmarks(sos_landmarks, "Right").shape[0] != 63:
        raise AssertionError("Landmark normalization must produce 63 features")

    positive_features = [1.0] * 63
    negative_features = [-1.0] * 63
    samples = [
        GestureSample(
            gesture="SOS",
            features=positive_features,
            handedness="Right",
            quality_score=0.92,
            frame_score=0.88,
            sample_index=index + 1,
            timestamp="2026-01-01T00:00:00Z",
            bbox={"x": 12, "y": 16, "w": 120, "h": 160},
            metadata={"source": "smoke-test"},
        )
        for index in range(12)
    ] + [
        GestureSample(
            gesture="_NEGATIVE",
            features=negative_features,
            handedness="Right",
            quality_score=0.92,
            frame_score=0.88,
            sample_index=index + 1,
            timestamp="2026-01-01T00:00:00Z",
            bbox={"x": 12, "y": 16, "w": 120, "h": 160},
            metadata={"source": "smoke-test"},
        )
        for index in range(12)
    ]
    bundle = train_model_bundle(samples, model_id="gesture_knn_smoke", n_neighbors=3)

    with tempfile.TemporaryDirectory() as tmpdir:
        model_dir = Path(tmpdir) / "gesture_knn_smoke"
        save_model_bundle(bundle, model_dir=model_dir, metrics={"accuracy": 1.0})
        loaded = load_model_bundle(model_dir)

        positive_prediction = loaded.predict(np.asarray(positive_features, dtype=np.float32))
        if positive_prediction.label != "SOS":
            raise AssertionError("Loaded bundle should predict SOS for the positive sample")
        negative_prediction = loaded.predict(np.asarray(negative_features, dtype=np.float32))
        if negative_prediction.label != "_NEGATIVE":
            raise AssertionError("Loaded bundle should predict _NEGATIVE for the negative sample")

        runtime = GestureRuntime(
            bundle=StaticBundle("SOS", 0.95, model_id="static-sos"),
            extractor=FakeExtractor(sos_landmarks),
            trigger_labels=("SOS",),
            min_confidence=0.50,
            confirmation_frames=3,
            confirmation_window=4,
            refresh_interval_frames=999,
        )

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        confirmed = False
        for _ in range(3):
            result = runtime.detect(frame)
            confirmed = confirmed or result.confirmed

        if not confirmed:
            raise AssertionError("Expected SOS confirmation from the synthetic runtime")

        runtime.extractor = FakeExtractor(negative_landmarks)
        runtime.bundle = StaticBundle("_NEGATIVE", 0.95, model_id="static-negative")
        runtime._recent_frames.clear()
        result = runtime.detect(frame)
        if result.confirmed:
            raise AssertionError("Negative gesture should not confirm as SOS")

    print("[OK] Phase 2 gesture runtime smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

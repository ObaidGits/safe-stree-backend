"""Shared dataclasses for the MediaPipe hand gesture pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GestureSample:
    gesture: str
    features: list[float]
    handedness: str = "Unknown"
    quality_score: float = 0.0
    frame_score: float = 0.0
    sample_index: int = 0
    timestamp: str = ""
    bbox: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GesturePrediction:
    label: str | None
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    feature_version: str = "landmark_63_v1"
    model_id: str = ""
    model_dir: str = ""
    engine: str = "mediapipe_landmark"
    classifier: str = "knn"
    hand_present: bool = False
    quality_score: float = 0.0


@dataclass(slots=True)
class GestureModelMetadata:
    model_id: str
    engine: str
    classifier: str
    feature_version: str
    created_at: str
    samples_per_class: dict[str, int]
    thresholds: dict[str, Any]
    metrics_file: str = "metrics.json"


@dataclass(slots=True)
class GestureRuntimeResult:
    hand_present: bool = False
    model_ready: bool = False
    detected: bool = False
    confirmed: bool = False
    label: str | None = None
    confidence: float = 0.0
    raw_confidence: float = 0.0
    quality_score: float = 0.0
    frame_score: float = 0.0
    handedness: str = "Unknown"
    model_id: str = ""
    model_dir: str = ""
    engine: str = "mediapipe_landmark"
    classifier: str = "knn"
    trigger_reason: str = ""
    window_count: int = 0
    positive_count: int = 0

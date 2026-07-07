"""Training, loading, and prediction helpers for landmark gesture models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_VERSION, HAND_FEATURE_SIZE
from .registry import ensure_gesture_storage_layout, load_json, save_json, utc_timestamp
from .schemas import GestureModelMetadata, GesturePrediction, GestureSample


@dataclass(slots=True)
class GestureModelBundle:
    model_id: str
    model_dir: Path
    scaler: StandardScaler
    classifier: KNeighborsClassifier
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def engine(self) -> str:
        return str(self.metadata.get("engine", "mediapipe_landmark"))

    @property
    def classifier_name(self) -> str:
        return str(self.metadata.get("classifier", "knn"))

    @property
    def feature_version(self) -> str:
        return str(self.metadata.get("featureVersion", FEATURE_VERSION))

    def predict(self, features: np.ndarray) -> GesturePrediction:
        vector = np.asarray(features, dtype=np.float32).reshape(1, -1)
        scaled = self.scaler.transform(vector)

        if hasattr(self.classifier, "predict_proba"):
            probabilities = self.classifier.predict_proba(scaled)[0]
            classes = list(self.classifier.classes_)
            best_index = int(np.argmax(probabilities))
            label = classes[best_index]
            confidence = float(probabilities[best_index])
            score_map = {str(cls): float(prob) for cls, prob in zip(classes, probabilities)}
        else:
            label = str(self.classifier.predict(scaled)[0])
            confidence = 1.0
            score_map = {label: 1.0}

        return GesturePrediction(
            label=str(label),
            confidence=max(0.0, min(1.0, confidence)),
            probabilities=score_map,
            feature_version=self.feature_version,
            model_id=self.model_id,
            model_dir=str(self.model_dir),
            engine=self.engine,
            classifier=self.classifier_name,
            hand_present=True,
        )


def _samples_to_arrays(samples: list[GestureSample]) -> tuple[np.ndarray, np.ndarray]:
    if not samples:
        raise ValueError("No gesture samples supplied")

    expected_size = len(samples[0].features)
    if expected_size != HAND_FEATURE_SIZE:
        raise ValueError(
            f"Expected {HAND_FEATURE_SIZE} features per sample, received {expected_size}"
        )

    for index, sample in enumerate(samples, start=1):
        if len(sample.features) != expected_size:
            raise ValueError(
                f"Sample {index} has {len(sample.features)} features, expected {expected_size}"
            )

    features = np.asarray([sample.features for sample in samples], dtype=np.float32)
    labels = np.asarray([sample.gesture for sample in samples], dtype=str)
    return features, labels


def _fit_knn(features: np.ndarray, labels: np.ndarray, n_neighbors: int = 5) -> tuple[StandardScaler, KNeighborsClassifier]:
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)
    neighbour_count = max(1, min(int(n_neighbors), len(features)))
    classifier = KNeighborsClassifier(n_neighbors=neighbour_count, weights="distance")
    classifier.fit(scaled_features, labels)
    return scaler, classifier


def train_model_bundle(
    samples: list[GestureSample],
    *,
    model_id: str,
    classifier_name: str = "knn",
    n_neighbors: int = 5,
    thresholds: dict[str, Any] | None = None,
) -> GestureModelBundle:
    if not samples:
        raise ValueError("No training samples supplied")

    ensure_gesture_storage_layout()
    features, labels = _samples_to_arrays(samples)

    if classifier_name != "knn":
        raise ValueError("Only knn classifier is implemented in Phase 2")

    scaler, classifier = _fit_knn(features, labels, n_neighbors=n_neighbors)

    class_counts: dict[str, int] = {}
    for label in labels:
        class_counts[str(label)] = class_counts.get(str(label), 0) + 1

    metadata = {
        "modelId": model_id,
        "engine": "mediapipe_landmark",
        "classifier": classifier_name,
        "featureVersion": FEATURE_VERSION,
        "createdAt": utc_timestamp(),
        "samplesPerClass": class_counts,
        "thresholds": thresholds
        or {
            "minConfidence": 0.80,
            "confirmationFrames": 10,
            "confirmationWindow": 12,
        },
        "metricsFile": "metrics.json",
    }

    return GestureModelBundle(
        model_id=model_id,
        model_dir=Path(),
        scaler=scaler,
        classifier=classifier,
        labels=sorted(class_counts.keys()),
        metadata=metadata,
    )


def save_model_bundle(
    bundle: GestureModelBundle,
    *,
    model_dir: Path,
    metrics: dict[str, Any],
) -> Path:
    ensure_gesture_storage_layout()
    model_dir = model_dir.resolve()
    model_dir.mkdir(parents=True, exist_ok=True)
    bundle.model_dir = model_dir

    joblib.dump(bundle.scaler, model_dir / "scaler.joblib")
    joblib.dump(bundle.classifier, model_dir / "model.joblib")

    save_json(model_dir / "labels.json", {"labels": bundle.labels})
    save_json(model_dir / "metrics.json", metrics)
    save_json(model_dir / "metadata.json", bundle.metadata)

    return model_dir


def load_model_bundle(model_dir: Path) -> GestureModelBundle:
    model_dir = model_dir.resolve()
    scaler = joblib.load(model_dir / "scaler.joblib")
    classifier = joblib.load(model_dir / "model.joblib")
    metadata = load_json(model_dir / "metadata.json") or {}
    labels_payload = load_json(model_dir / "labels.json") or {}
    labels = [str(label) for label in labels_payload.get("labels", [])]
    model_id = str(metadata.get("modelId", model_dir.name))

    return GestureModelBundle(
        model_id=model_id,
        model_dir=model_dir,
        scaler=scaler,
        classifier=classifier,
        labels=labels,
        metadata=metadata,
    )

"""Evaluation helpers for the MediaPipe landmark gesture pipeline."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .classifier import train_model_bundle
from .registry import LOGS_ROOT, ensure_gesture_storage_layout, save_json
from .schemas import GestureSample


def _build_confusion_matrix(labels: list[str]) -> dict[str, dict[str, int]]:
    return {row: {col: 0 for col in labels} for row in labels}


def _metrics_from_confusion(labels: list[str], confusion: dict[str, dict[str, int]]) -> tuple[dict[str, Any], dict[str, float]]:
    metrics: dict[str, Any] = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[row][label] for row in labels if row != label)
        fn = sum(confusion[label][col] for col in labels if col != label)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        metrics[label] = {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "support": int(sum(confusion[label].values())),
        }

    macro_precision = np.mean([entry["precision"] for entry in metrics.values()]) if metrics else 0.0
    macro_recall = np.mean([entry["recall"] for entry in metrics.values()]) if metrics else 0.0
    macro_f1 = np.mean([entry["f1"] for entry in metrics.values()]) if metrics else 0.0

    return metrics, {
        "macro_precision": round(float(macro_precision), 4),
        "macro_recall": round(float(macro_recall), 4),
        "macro_f1": round(float(macro_f1), 4),
    }


def build_evaluation_report(samples: list[GestureSample], *, n_neighbors: int = 5) -> dict[str, Any]:
    ensure_gesture_storage_layout()
    if len(samples) < 2:
        raise ValueError("Need at least two samples to evaluate a gesture model")

    labels = sorted({sample.gesture for sample in samples})
    confusion = _build_confusion_matrix(labels)
    class_counts = Counter(sample.gesture for sample in samples)

    correct = 0
    total = 0

    for index, held_out_sample in enumerate(samples):
        train_samples = [sample for sample_index, sample in enumerate(samples) if sample_index != index]
        if not train_samples:
            continue

        bundle = train_model_bundle(
            train_samples,
            model_id=f"loo_{index:04d}",
            n_neighbors=n_neighbors,
        )
        prediction = bundle.predict(np.asarray(held_out_sample.features, dtype=np.float32))
        predicted_label = str(prediction.label or "")
        true_label = str(held_out_sample.gesture)

        if true_label not in confusion:
            continue
        if predicted_label not in confusion[true_label]:
            predicted_label = labels[0]

        confusion[true_label][predicted_label] += 1
        correct += int(predicted_label == true_label)
        total += 1

    accuracy = (correct / total) if total else 0.0
    per_class, macro = _metrics_from_confusion(labels, confusion)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sampleCount": total,
        "labels": labels,
        "classCounts": dict(sorted(class_counts.items())),
        "accuracy": round(float(accuracy), 4),
        "perClass": per_class,
        "macro": macro,
        "confusionMatrix": confusion,
        "evaluation": "leave_one_out",
        "nNeighbors": int(n_neighbors),
    }
    return report


def save_evaluation_report(report: dict[str, Any], *, prefix: str = "gesture_evaluation") -> Path:
    ensure_gesture_storage_layout()
    report_path = LOGS_ROOT / f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    save_json(report_path, report)
    return report_path

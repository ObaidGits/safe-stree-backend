"""
Lightweight evaluation utility for the OpenCV gesture template model.
Calculates confusion matrix and per-class precision/recall/F1 via leave-one-out scoring.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from sos_gesture.gesture_detector import SimpleGestureDetector

MODEL_PATH = Path("data/gestures/gestures.json")
LOGS_DIR = Path("data/logs")


def load_samples(model_path):
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    with open(model_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    gestures = data.get("gestures", {})
    samples = []
    for label, vectors in gestures.items():
        for vector in vectors:
            samples.append((label, vector))
    return samples


def predict_label(detector, test_vector, train_samples):
    if not train_samples:
        return None, 0.0

    class_scores = {}
    by_class = {}
    for label, features in train_samples:
        by_class.setdefault(label, []).append(features)

    for label, feature_list in by_class.items():
        scores = [detector.compare_features(test_vector, features) for features in feature_list]
        class_scores[label] = float(np.mean(scores)) if scores else 0.0

    best_label = max(class_scores, key=class_scores.get)
    best_score = class_scores[best_label]
    return best_label, best_score


def compute_metrics(labels, confusion):
    metrics = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in labels if other != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        metrics[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": int(sum(confusion[label].values())),
        }

    macro_precision = np.mean([m["precision"] for m in metrics.values()]) if metrics else 0.0
    macro_recall = np.mean([m["recall"] for m in metrics.values()]) if metrics else 0.0
    macro_f1 = np.mean([m["f1"] for m in metrics.values()]) if metrics else 0.0

    return metrics, {
        "macro_precision": round(float(macro_precision), 4),
        "macro_recall": round(float(macro_recall), 4),
        "macro_f1": round(float(macro_f1), 4),
    }


def evaluate():
    detector = SimpleGestureDetector(model_file=str(MODEL_PATH))
    samples = load_samples(MODEL_PATH)

    if len(samples) < 2:
        raise RuntimeError("Need at least 2 samples to evaluate")

    labels = sorted({label for label, _ in samples})
    confusion = {row: {col: 0 for col in labels} for row in labels}

    correct = 0
    total = 0

    for idx, (true_label, test_vector) in enumerate(samples):
        train_samples = [sample for j, sample in enumerate(samples) if j != idx]
        pred_label, _ = predict_label(detector, test_vector, train_samples)
        if pred_label is None:
            continue

        confusion[true_label][pred_label] += 1
        correct += int(pred_label == true_label)
        total += 1

    accuracy = (correct / total) if total > 0 else 0.0
    per_class, macro = compute_metrics(labels, confusion)

    report = {
        "timestamp": datetime.now().isoformat(),
        "samples": total,
        "labels": labels,
        "accuracy": round(float(accuracy), 4),
        "per_class": per_class,
        "macro": macro,
        "confusion_matrix": confusion,
    }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = LOGS_DIR / f"gesture_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== Gesture Evaluation Summary ===")
    print(f"Samples: {total}")
    print(f"Accuracy: {report['accuracy']:.2%}")
    print(f"Macro Precision: {macro['macro_precision']:.4f}")
    print(f"Macro Recall:    {macro['macro_recall']:.4f}")
    print(f"Macro F1:        {macro['macro_f1']:.4f}")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    evaluate()

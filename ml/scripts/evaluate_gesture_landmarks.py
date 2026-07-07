#!/usr/bin/env python3
"""Evaluate the recorded landmark gesture dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.hand_gesture.evaluator import build_evaluation_report, save_evaluation_report
from pipelines.hand_gesture.trainer import load_dataset_samples


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the SafeStree landmark gesture dataset")
    parser.add_argument("--n-neighbors", type=int, default=5, help="KNN neighbors used during evaluation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples = load_dataset_samples()
    if len(samples) < 2:
        print("[ERROR] Need at least two samples before evaluation")
        return 1

    report = build_evaluation_report(samples, n_neighbors=args.n_neighbors)
    report_path = save_evaluation_report(report, prefix="gesture_validation")

    print("=" * 72)
    print("Gesture dataset evaluation")
    print("=" * 72)
    print(f"Samples: {report['sampleCount']}")
    print(f"Labels: {report['labels']}")
    print(f"Accuracy: {report['accuracy']:.2%}")
    print(f"Macro F1: {report['macro']['macro_f1']:.4f}")
    print(f"Report: {report_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline smoke test for the SafeStree gender estimation pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.gender_detection.runtime import GenderFaceEstimate, GenderSceneRuntime, normalize_gender_label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline gender detection checks")
    parser.add_argument("--offline", action="store_true", help="Run without OpenVINO models")
    return parser.parse_args()


class FakeGenderBackend:
    ready = True
    source = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def detect(self, frame: np.ndarray):
        self.calls += 1
        if self.calls == 1:
            return [
                GenderFaceEstimate(
                    bbox={"left": 10, "top": 10, "right": 100, "bottom": 120},
                    face_confidence=0.96,
                    gender_label="male",
                    gender_confidence=0.94,
                    age=24.0,
                    source="fake",
                ),
                GenderFaceEstimate(
                    bbox={"left": 120, "top": 12, "right": 220, "bottom": 130},
                    face_confidence=0.95,
                    gender_label="female",
                    gender_confidence=0.93,
                    age=22.0,
                    source="fake",
                ),
            ]
        return []

    def close(self) -> None:
        return None


def run_offline_checks() -> None:
    assert normalize_gender_label("Man") == "male"
    assert normalize_gender_label("Woman") == "female"
    assert normalize_gender_label("unknown") == "unknown"

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    runtime = GenderSceneRuntime(
        backend=FakeGenderBackend(),
        enabled=True,
        engine="openvino",
        analyze_every_n_frames=1,
        smoothing_window=2,
        max_faces=4,
    )

    summary1 = runtime.detect(frame, frame_count=1, fps=12.0)
    assert summary1.ready is True
    assert summary1.detected is True
    assert summary1.source == "fake"
    assert summary1.face_count == 2
    assert summary1.male_count == 1
    assert summary1.female_count == 1
    assert summary1.unknown_gender_count == 0
    payload1 = summary1.to_payload()
    assert payload1["genderEstimateLabel"] == "estimated"
    assert payload1["genderEngine"] == "fake"
    assert summary1.faces[0].to_payload()["genderLabel"] == "male"

    summary2 = runtime.detect(frame, frame_count=2, fps=12.0)
    assert summary2.raw_face_count == 0
    assert summary2.face_count == 1, "Expected smoothing to keep the estimate stable"
    payload = summary2.to_payload()
    assert payload["faceCount"] == 1
    assert payload["maleCount"] == 0 or payload["maleCount"] == 1
    assert payload["genderEstimate"] is True
    assert payload["genderEngine"] == "fake"

    unknown_face = GenderFaceEstimate(
        bbox={"left": 0, "top": 0, "right": 48, "bottom": 48},
        face_confidence=0.45,
        gender_label="unknown",
        gender_confidence=0.0,
        source="fake",
    )
    unknown_payload = unknown_face.to_payload()
    assert unknown_payload["genderLabel"] == "unknown"
    assert unknown_payload["faceConfidence"] == 0.45


def main() -> int:
    parse_args()
    run_offline_checks()
    print("[OK] Offline gender detection smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

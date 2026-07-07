"""Landmark feature normalization and quality scoring."""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np


FEATURE_VERSION = "landmark_63_v1"
HAND_LANDMARK_COUNT = 21
HAND_FEATURE_SIZE = HAND_LANDMARK_COUNT * 3


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _estimate_hand_scale(points: np.ndarray) -> float:
    wrist = points[0, :2]
    anchor_indices = (5, 9, 13, 17)
    distances = [np.linalg.norm(points[idx, :2] - wrist) for idx in anchor_indices if idx < len(points)]
    scale = max([float(distance) for distance in distances if distance > 0.0] or [1.0])
    return max(scale, 1e-6)


def normalize_landmarks(landmarks: np.ndarray, handedness: str = "Unknown") -> np.ndarray:
    """Convert 21 hand landmarks to a stable 63-value feature vector."""

    points = np.asarray(landmarks, dtype=np.float32)
    if points.shape != (HAND_LANDMARK_COUNT, 3):
        raise ValueError(f"Expected {HAND_LANDMARK_COUNT} landmarks with xyz coordinates, got {points.shape}")

    centered = points.copy()
    wrist = centered[0].copy()
    centered[:, 0] -= wrist[0]
    centered[:, 1] -= wrist[1]
    centered[:, 2] -= wrist[2]

    scale = _estimate_hand_scale(centered)
    centered[:, 0] /= scale
    centered[:, 1] /= scale
    centered[:, 2] /= scale

    if handedness.strip().lower() == "left":
        centered[:, 0] *= -1.0

    return centered.reshape(-1).astype(np.float32)


def frame_blur_score(frame: np.ndarray) -> float:
    if frame is None or frame.size == 0:
        return 0.0

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return _clamp(variance / 400.0, 0.0, 1.0)


def bbox_quality_score(bbox: tuple[int, int, int, int], frame_size: tuple[int, int]) -> float:
    frame_h, frame_w = frame_size
    x, y, w, h = bbox
    if frame_h <= 0 or frame_w <= 0 or w <= 0 or h <= 0:
        return 0.0

    area_ratio = (w * h) / float(frame_w * frame_h)
    # Prefer a hand that is visible but not extremely large or tiny.
    area_score = 1.0 - min(1.0, abs(area_ratio - 0.08) / 0.08)

    border_margin = min(x, y, frame_w - (x + w), frame_h - (y + h))
    border_score = _clamp(border_margin / float(min(frame_w, frame_h) * 0.12), 0.0, 1.0)

    return _clamp((0.65 * area_score) + (0.35 * border_score), 0.0, 1.0)


def sample_quality_score(
    *,
    bbox: tuple[int, int, int, int],
    frame_size: tuple[int, int],
    handedness_score: float = 0.0,
    blur_score: float = 0.0,
) -> float:
    size_score = bbox_quality_score(bbox, frame_size)
    return _clamp(
        (0.45 * size_score)
        + (0.25 * _clamp(handedness_score, 0.0, 1.0))
        + (0.30 * _clamp(blur_score, 0.0, 1.0)),
        0.0,
        1.0,
    )


def feature_stability_score(feature_window: Iterable[np.ndarray]) -> float:
    """Return a 0-1 score that increases when consecutive landmark vectors stay similar."""

    vectors = [np.asarray(item, dtype=np.float32) for item in feature_window if item is not None]
    if len(vectors) < 3:
        return 0.0

    stack = np.stack(vectors, axis=0)
    deltas = np.linalg.norm(np.diff(stack, axis=0), axis=1)
    average_delta = float(np.mean(deltas)) if deltas.size else 0.0
    return _clamp(1.0 - (average_delta / 1.25), 0.0, 1.0)


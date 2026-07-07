"""MediaPipe hand landmark extraction and overlay helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import mediapipe as mp
import numpy as np


@dataclass(slots=True)
class HandObservation:
    landmarks: np.ndarray
    handedness: str
    handedness_score: float
    bbox: tuple[int, int, int, int]
    frame_size: tuple[int, int]
    raw_landmarks: Any = None


class HandLandmarkExtractor:
    """Wrap MediaPipe Hands and expose the primary hand as a normalized frame observation."""

    def __init__(
        self,
        *,
        max_num_hands: int = 1,
        model_complexity: int = 0,
        min_detection_confidence: float = 0.65,
        min_tracking_confidence: float = 0.65,
    ) -> None:
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self._hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max(1, int(max_num_hands)),
            model_complexity=int(model_complexity),
            min_detection_confidence=float(min_detection_confidence),
            min_tracking_confidence=float(min_tracking_confidence),
        )

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, int(value)))

    @staticmethod
    def _landmarks_to_array(hand_landmarks) -> np.ndarray:
        return np.array([[lm.x, lm.y, lm.z] for lm in hand_landmarks.landmark], dtype=np.float32)

    @staticmethod
    def _compute_bbox(landmarks: np.ndarray, frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
        frame_h, frame_w = frame_size
        xs = np.clip(landmarks[:, 0] * frame_w, 0, max(frame_w - 1, 0))
        ys = np.clip(landmarks[:, 1] * frame_h, 0, max(frame_h - 1, 0))

        x_min = int(np.floor(xs.min())) if xs.size else 0
        y_min = int(np.floor(ys.min())) if ys.size else 0
        x_max = int(np.ceil(xs.max())) if xs.size else 0
        y_max = int(np.ceil(ys.max())) if ys.size else 0

        return x_min, y_min, max(1, x_max - x_min), max(1, y_max - y_min)

    def extract(self, frame: np.ndarray) -> HandObservation | None:
        if frame is None or frame.size == 0:
            return None

        frame_h, frame_w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb_frame)

        if not results.multi_hand_landmarks:
            return None

        hand_landmarks = results.multi_hand_landmarks[0]
        handedness = "Unknown"
        handedness_score = 0.0
        if results.multi_handedness:
            classification = results.multi_handedness[0].classification[0]
            handedness = getattr(classification, "label", "Unknown") or "Unknown"
            handedness_score = float(getattr(classification, "score", 0.0) or 0.0)

        landmarks = self._landmarks_to_array(hand_landmarks)
        bbox = self._compute_bbox(landmarks, (frame_h, frame_w))

        return HandObservation(
            landmarks=landmarks,
            handedness=handedness,
            handedness_score=handedness_score,
            bbox=bbox,
            frame_size=(frame_h, frame_w),
            raw_landmarks=hand_landmarks,
        )

    def draw(self, frame: np.ndarray, observation: HandObservation | None, color=(0, 255, 0)) -> np.ndarray:
        if frame is None or observation is None:
            return frame

        if observation.raw_landmarks is not None:
            self.mp_draw.draw_landmarks(
                frame,
                observation.raw_landmarks,
                self.mp_hands.HAND_CONNECTIONS,
                self.mp_draw.DrawingSpec(color=color, thickness=2, circle_radius=2),
                self.mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2),
            )

        x, y, w, h = observation.bbox
        frame_h, frame_w = observation.frame_size
        x = self._clamp(x, 0, max(frame_w - 1, 0))
        y = self._clamp(y, 0, max(frame_h - 1, 0))
        w = self._clamp(w, 1, frame_w - x if frame_w > x else w)
        h = self._clamp(h, 1, frame_h - y if frame_h > y else h)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

        label = f"{observation.handedness} {observation.handedness_score:.2f}"
        cv2.putText(
            frame,
            label,
            (x, max(20, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

        return frame

    def close(self) -> None:
        try:
            self._hands.close()
        except Exception:
            pass


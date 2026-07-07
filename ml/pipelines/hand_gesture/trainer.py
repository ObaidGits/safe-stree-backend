"""Training helpers for the MediaPipe landmark gesture pipeline."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import cv2

from config import GESTURE_TRAIN_MIN_SAMPLES_PER_CLASS

from .classifier import GestureModelBundle, save_model_bundle, train_model_bundle
from .evaluator import build_evaluation_report
from .features import frame_blur_score, normalize_landmarks, sample_quality_score
from .landmarks import HandLandmarkExtractor
from .registry import (
    LOGS_ROOT,
    MODEL_ROOT,
    RAW_SESSIONS_ROOT,
    TRAINING_ROOT,
    activate_model,
    ensure_gesture_storage_layout,
    model_id_from_time,
    save_json,
    utc_timestamp,
)
from .schemas import GestureSample


Logger = Callable[[str], None]

DATASET_PATH = TRAINING_ROOT / "dataset.jsonl"


def normalize_gesture_label(label: str) -> str:
    cleaned = str(label or "").strip().upper().replace(" ", "_")
    aliases = {
        "NEGATIVE": "_NEGATIVE",
        "NON_SOS": "_NEGATIVE",
        "NO_GESTURE": "_NEGATIVE",
        "BACKGROUND": "_NEGATIVE",
    }
    return aliases.get(cleaned, cleaned)


def sample_to_record(sample: GestureSample) -> dict[str, Any]:
    return asdict(sample)


def sample_from_record(record: dict[str, Any]) -> GestureSample:
    bbox = record.get("bbox") or {}
    metadata = record.get("metadata") or {}
    return GestureSample(
        gesture=normalize_gesture_label(record.get("gesture", "")),
        features=[float(value) for value in record.get("features", [])],
        handedness=str(record.get("handedness", "Unknown")),
        quality_score=float(record.get("quality_score", 0.0)),
        frame_score=float(record.get("frame_score", 0.0)),
        sample_index=int(record.get("sample_index", 0)),
        timestamp=str(record.get("timestamp", "")),
        bbox={str(key): int(value) for key, value in bbox.items()},
        metadata={str(key): value for key, value in metadata.items()},
    )


def _load_jsonl_samples(path: Path) -> list[GestureSample]:
    if not path.exists():
        return []

    samples: list[GestureSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                samples.append(sample_from_record(json.loads(raw)))
            except Exception:
                continue
    return samples


def load_dataset_samples() -> list[GestureSample]:
    ensure_gesture_storage_layout()
    if DATASET_PATH.exists():
        return _load_jsonl_samples(DATASET_PATH)

    session_samples: list[GestureSample] = []
    for sample_file in RAW_SESSIONS_ROOT.rglob("samples.jsonl"):
        session_samples.extend(_load_jsonl_samples(sample_file))
    return session_samples


def _write_jsonl(path: Path, samples: Iterable[GestureSample], *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample_to_record(sample), ensure_ascii=True))
            handle.write("\n")


def save_session_samples(
    session_id: str,
    samples: list[GestureSample],
    *,
    session_metadata: dict[str, Any] | None = None,
) -> Path:
    ensure_gesture_storage_layout()
    session_dir = RAW_SESSIONS_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(session_dir / "samples.jsonl", samples, append=False)
    _write_jsonl(DATASET_PATH, samples, append=True)

    metadata = {
        "sessionId": session_id,
        "sampleCount": len(samples),
        "createdAt": utc_timestamp(),
    }
    if session_metadata:
        metadata.update(session_metadata)
    save_json(session_dir / "session.json", metadata)
    return session_dir


class GestureSampleRecorder:
    """Capture stable hand landmarks and convert them into training samples."""

    def __init__(
        self,
        *,
        extractor: HandLandmarkExtractor | None = None,
        min_quality: float = 0.60,
        stabilization_frames: int = 4,
        sample_stride: int = 2,
        logger: Logger | None = None,
    ) -> None:
        self.extractor = extractor or HandLandmarkExtractor()
        self.min_quality = max(0.0, min(1.0, float(min_quality)))
        self.stabilization_frames = max(1, int(stabilization_frames))
        self.sample_stride = max(1, int(sample_stride))
        self.logger = logger or (lambda message: print(message))

    def close(self) -> None:
        self.extractor.close()

    def _build_sample(
        self,
        *,
        gesture: str,
        features: list[float],
        handedness: str,
        quality_score: float,
        frame_score: float,
        sample_index: int,
        bbox: tuple[int, int, int, int],
        metadata: dict[str, Any],
    ) -> GestureSample:
        x, y, w, h = bbox
        return GestureSample(
            gesture=normalize_gesture_label(gesture),
            features=[float(value) for value in features],
            handedness=handedness,
            quality_score=float(quality_score),
            frame_score=float(frame_score),
            sample_index=sample_index,
            timestamp=utc_timestamp(),
            bbox={"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
            metadata=metadata,
        )

    @staticmethod
    def _draw_progress_bar(frame, progress: float, *, label: str, color=(0, 200, 0)) -> None:
        if frame is None:
            return

        height, width = frame.shape[:2]
        bar_width = max(220, min(width - 40, 520))
        bar_height = 18
        x = 20
        y = 20
        progress = max(0.0, min(1.0, float(progress)))

        cv2.rectangle(frame, (x, y), (x + bar_width, y + bar_height), (40, 40, 40), -1)
        cv2.rectangle(frame, (x, y), (x + int(bar_width * progress), y + bar_height), color, -1)
        cv2.rectangle(frame, (x, y), (x + bar_width, y + bar_height), (255, 255, 255), 1)

        text = f"{label} {int(progress * 100)}%"
        cv2.putText(
            frame,
            text,
            (x, y + bar_height + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )

    @staticmethod
    def _show_countdown(frame: Any, seconds: int, window_name: str) -> None:
        if seconds <= 0:
            return

        working_frame = frame.copy() if frame is not None else None
        for remaining in range(seconds, 0, -1):
            if working_frame is not None:
                overlay = working_frame.copy()
                cv2.rectangle(overlay, (0, 0), (overlay.shape[1], overlay.shape[0]), (0, 0, 0), -1)
                cv2.addWeighted(overlay, 0.55, working_frame, 0.45, 0, working_frame)
                message = f"Hold gesture - starting in {remaining}"
                cv2.putText(
                    working_frame,
                    message,
                    (30, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (255, 255, 255),
                    2,
                )
                cv2.imshow(window_name, working_frame)
                cv2.waitKey(1000)

    def collect_samples(
        self,
        cap: cv2.VideoCapture,
        *,
        gesture: str,
        target_samples: int,
        auto: bool = True,
        display: bool = True,
        window_name: str = "Gesture Training",
        countdown_seconds: int = 3,
        rotation_prompt_interval: int = 30,
    ) -> tuple[list[GestureSample], str]:
        if not auto and not display:
            raise ValueError("Manual capture requires display=True")

        gesture_label = normalize_gesture_label(gesture)
        session_id = f"{gesture_label.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        samples: list[GestureSample] = []
        stable_frames = 0
        frame_index = 0
        last_capture_frame = -self.sample_stride
        paused = False
        rotation_prompt_interval = max(1, int(rotation_prompt_interval))

        initial_success, initial_frame = cap.read()
        if display and auto and initial_success and initial_frame is not None:
            self._show_countdown(initial_frame, int(countdown_seconds), window_name)
        elif int(countdown_seconds) > 0:
            for remaining in range(int(countdown_seconds), 0, -1):
                self.logger(f"[Training] {gesture_label} starts in {remaining}")

        buffered_frame = None

        try:
            while len(samples) < int(target_samples):
                if buffered_frame is not None:
                    frame = buffered_frame
                    success = True
                    buffered_frame = None
                else:
                    success, frame = cap.read()

                if not success or frame is None:
                    continue

                frame = cv2.flip(frame, 1)
                display_frame = frame.copy()
                frame_score = frame_blur_score(frame)
                observation = self.extractor.extract(frame)
                rotation_hint = len(samples) > 0 and (len(samples) % rotation_prompt_interval == 0)

                if observation is None:
                    stable_frames = 0
                    if display:
                        cv2.putText(
                            display_frame,
                            "No hand detected",
                            (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0, 0, 255),
                            2,
                        )
                else:
                    quality_score = sample_quality_score(
                        bbox=observation.bbox,
                        frame_size=observation.frame_size,
                        handedness_score=observation.handedness_score,
                        blur_score=frame_score,
                    )
                    if quality_score >= self.min_quality:
                        stable_frames += 1
                    else:
                        stable_frames = 0

                    features = normalize_landmarks(observation.landmarks, observation.handedness)
                    self.extractor.draw(display_frame, observation)

                    can_auto_capture = (
                        auto
                        and not paused
                        and stable_frames >= self.stabilization_frames
                        and (frame_index - last_capture_frame) >= self.sample_stride
                    )
                    if can_auto_capture:
                        sample = self._build_sample(
                            gesture=gesture_label,
                            features=features.tolist(),
                            handedness=observation.handedness,
                            quality_score=quality_score,
                            frame_score=frame_score,
                            sample_index=len(samples) + 1,
                            bbox=observation.bbox,
                            metadata={
                                "auto": True,
                                "sessionId": session_id,
                                "featureVersion": "landmark_63_v1",
                            },
                            )
                        samples.append(sample)
                        last_capture_frame = frame_index
                        self.logger(
                            f"[Training] Captured {gesture_label}: {len(samples)}/{target_samples} "
                            f"(quality={quality_score:.2f})"
                        )

                    if display:
                        status = (
                            f"{gesture_label} | quality={quality_score:.0%} | stable={stable_frames}/{self.stabilization_frames}"
                        )
                        cv2.putText(
                            display_frame,
                            status,
                            (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 0) if quality_score >= self.min_quality else (0, 165, 255),
                            2,
                        )
                        cv2.putText(
                            display_frame,
                            f"samples={len(samples)}/{target_samples}",
                            (10, 65),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 0),
                            2,
                        )
                        self._draw_progress_bar(
                            display_frame,
                            len(samples) / float(max(1, target_samples)),
                            label="Training progress",
                            color=(0, 180, 255),
                        )
                        if rotation_hint:
                            cv2.putText(
                                display_frame,
                                "Rotate hand slightly for variation",
                                (10, 120),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (0, 255, 255),
                                2,
                            )
                        if paused:
                            cv2.putText(
                                display_frame,
                                "Auto capture paused",
                                (10, 150),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (0, 165, 255),
                                2,
                            )

                        if not auto:
                            cv2.putText(
                                display_frame,
                                "SPACE to capture | ESC/q to stop",
                                (10, 95),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                (255, 255, 255),
                                2,
                            )
                        else:
                            cv2.putText(
                                display_frame,
                                "SPACE pause/resume | R restart | Q quit",
                                (10, 180),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                (255, 255, 255),
                                2,
                            )

                        cv2.imshow(window_name, display_frame)
                        key = cv2.waitKey(1) & 0xFF
                        if key in {27, ord("q")}:
                            break
                        if auto and key == 32:
                            paused = not paused
                            self.logger(
                                "[Training] Auto capture resumed" if not paused else "[Training] Auto capture paused"
                            )
                        if key == ord("r"):
                            self.logger(f"[Training] Restarting {gesture_label} capture")
                            samples.clear()
                            stable_frames = 0
                            frame_index = 0
                            last_capture_frame = -self.sample_stride
                            paused = False
                            continue
                        if not auto and key == 32 and quality_score >= self.min_quality:
                            sample = self._build_sample(
                                gesture=gesture_label,
                                features=features.tolist(),
                                handedness=observation.handedness,
                                quality_score=quality_score,
                                frame_score=frame_score,
                                sample_index=len(samples) + 1,
                                bbox=observation.bbox,
                                metadata={
                                    "auto": False,
                                    "sessionId": session_id,
                                    "featureVersion": "landmark_63_v1",
                                },
                            )
                            samples.append(sample)
                            self.logger(
                                f"[Training] Captured {gesture_label}: {len(samples)}/{target_samples} "
                                f"(manual capture)"
                            )
                    else:
                        if not auto and display:
                            cv2.putText(
                                display_frame,
                                "Wait for quality gate before SPACE",
                                (10, 95),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65,
                                (0, 255, 255),
                                2,
                            )

                frame_index += 1

                if not display:
                    continue

            return samples, session_id
        finally:
            if display:
                try:
                    cv2.destroyWindow(window_name)
                except Exception:
                    pass


def collect_gesture_samples(
    cap: cv2.VideoCapture,
    *,
    gesture: str,
    target_samples: int,
    auto: bool = True,
    min_quality: float = 0.60,
    stabilization_frames: int = 4,
    sample_stride: int = 2,
    display: bool = True,
    window_name: str = "Gesture Training",
    countdown_seconds: int = 3,
    rotation_prompt_interval: int = 30,
    logger: Logger | None = None,
) -> tuple[list[GestureSample], str]:
    recorder = GestureSampleRecorder(
        min_quality=min_quality,
        stabilization_frames=stabilization_frames,
        sample_stride=sample_stride,
        logger=logger,
    )
    try:
        return recorder.collect_samples(
            cap,
            gesture=gesture,
            target_samples=target_samples,
            auto=auto,
            display=display,
            window_name=window_name,
            countdown_seconds=countdown_seconds,
            rotation_prompt_interval=rotation_prompt_interval,
        )
    finally:
        recorder.close()


def summarize_samples(samples: list[GestureSample]) -> dict[str, Any]:
    counts = Counter(sample.gesture for sample in samples)
    return {
        "sampleCount": len(samples),
        "classCounts": dict(sorted(counts.items())),
        "featureVersion": "landmark_63_v1",
    }


def train_and_activate_model(
    samples: list[GestureSample],
    *,
    force: bool = False,
    model_id: str | None = None,
    n_neighbors: int = 5,
    min_accuracy: float = 0.85,
    min_macro_f1: float = 0.80,
    auto_activate: bool = True,
) -> dict[str, Any]:
    ensure_gesture_storage_layout()
    if not samples:
        raise ValueError("No gesture samples available")

    normalized_samples = [
        GestureSample(
            gesture=normalize_gesture_label(sample.gesture),
            features=[float(value) for value in sample.features],
            handedness=sample.handedness,
            quality_score=sample.quality_score,
            frame_score=sample.frame_score,
            sample_index=sample.sample_index,
            timestamp=sample.timestamp,
            bbox=dict(sample.bbox),
            metadata=dict(sample.metadata),
        )
        for sample in samples
    ]

    counts = Counter(sample.gesture for sample in normalized_samples)
    if len(counts) < 2 and not force:
        raise ValueError("Need at least two gesture classes before activating a model")

    weak_classes = [
        label for label, count in counts.items() if count < GESTURE_TRAIN_MIN_SAMPLES_PER_CLASS
    ]
    if weak_classes and not force:
        raise ValueError(
            "Not enough samples per class for: "
            + ", ".join(sorted(weak_classes))
            + f". Minimum per class is {GESTURE_TRAIN_MIN_SAMPLES_PER_CLASS}."
        )

    report = build_evaluation_report(normalized_samples, n_neighbors=n_neighbors)
    report["qualityGate"] = {
        "minSamplesPerClass": GESTURE_TRAIN_MIN_SAMPLES_PER_CLASS,
        "minAccuracy": min_accuracy,
        "minMacroF1": min_macro_f1,
        "force": bool(force),
        "passed": bool(
            report["sampleCount"] > 0
            and report["accuracy"] >= min_accuracy
            and report["macro"]["macro_f1"] >= min_macro_f1
            and len(counts) >= 2
            and not weak_classes
        ),
    }

    bundle_id = model_id or model_id_from_time()
    bundle = train_model_bundle(
        normalized_samples,
        model_id=bundle_id,
        n_neighbors=n_neighbors,
        thresholds={
            "minConfidence": 0.80,
            "confirmationFrames": 10,
            "confirmationWindow": 12,
        },
    )

    model_dir = MODEL_ROOT / bundle_id
    save_model_bundle(bundle, model_dir=model_dir, metrics=report)
    bundle.model_dir = model_dir

    activation_allowed = report["qualityGate"]["passed"] or force
    if activation_allowed and auto_activate:
        activate_model(model_dir, model_id=bundle_id)
        report["activated"] = True
    else:
        report["activated"] = False

    report["modelId"] = bundle_id
    report["modelDir"] = str(model_dir)
    report["sampleSummary"] = summarize_samples(normalized_samples)
    report["activationAllowed"] = bool(activation_allowed)
    report["activationDeferred"] = bool(activation_allowed and not auto_activate)

    save_json(
        LOGS_ROOT / f"gesture_training_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
        report,
    )
    return {
        "bundle": bundle,
        "modelDir": model_dir,
        "modelId": bundle_id,
        "report": report,
        "activated": bool(report["activated"]),
    }

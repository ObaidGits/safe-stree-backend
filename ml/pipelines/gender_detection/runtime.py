"""Local scene gender estimation for SafeStree.

Phase 5 keeps gender estimation local and optional. The primary path uses
OpenVINO face detection plus the age/gender model from Open Model Zoo. If that
stack is unavailable, a DeepFace fallback can be enabled when installed.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import mean
from threading import Lock
from time import time
from typing import Any, Iterable, Protocol

import cv2
import numpy as np

from config import (
    FACE_MODEL_PATH,
    FACE_MODEL_VERSION,
    GENDER_ANALYZE_EVERY_N_FRAMES,
    GENDER_CROP_MARGIN,
    GENDER_DETECTION_ENABLED,
    GENDER_DEVICE,
    GENDER_ENGINE,
    GENDER_MAX_FACES,
    GENDER_MIN_FACE_CONFIDENCE,
    GENDER_MIN_GENDER_CONFIDENCE,
    GENDER_MODEL_PATH,
    GENDER_MODEL_VERSION,
    GENDER_SMOOTHING_WINDOW,
    GENDER_USE_DEEPFACE_FALLBACK,
)


Logger = Any

try:  # pragma: no cover - optional dependency
    import openvino as ov
except Exception:  # pragma: no cover - optional dependency
    ov = None


def normalize_gender_label(raw_value: str | None) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"male", "man", "m", "boy"}:
        return "male"
    if value in {"female", "woman", "f", "girl"}:
        return "female"
    return "unknown"


def _log(logger: Logger | None, message: str, prefix: str = "INFO") -> None:
    if logger is None:
        print(f"[{prefix}] {message}")
        return
    logger(message, prefix)


def _clamp_int(value: float | int | None, default: int = 0) -> int:
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return max(0, int(default))


def _clamp_float(value: float | int | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _port_name(port: Any) -> str:
    for attr in ("any_name", "get_any_name"):
        if hasattr(port, attr):
            value = getattr(port, attr)
            return value() if callable(value) else str(value)
    return str(port)


def _resolve_model_xml_path(model_path: str | Path, default_stem: str) -> Path:
    """Resolve a model path to an OpenVINO XML file."""

    path = Path(model_path)

    search_roots = []
    if path.exists() and path.is_dir():
        search_roots.append(path)
    if path.parent.exists():
        search_roots.append(path.parent)
    if path.parent.parent.exists():
        search_roots.append(path.parent.parent)

    if path.is_file():
        if path.suffix.lower() == ".xml":
            return path
        if path.suffix.lower() == ".bin":
            candidate = path.with_suffix(".xml")
            if candidate.exists():
                return candidate
            return candidate
        candidate = path.with_suffix(".xml")
        if candidate.exists():
            return candidate
        return candidate

    if path.is_dir():
        named = path / f"{default_stem}.xml"
        if named.exists():
            return named
        recursive_matches = sorted(path.rglob(f"{default_stem}.xml"))
        if recursive_matches:
            return recursive_matches[0]
        xml_files = sorted(path.rglob("*.xml"))
        if len(xml_files) == 1:
            return xml_files[0]

    for root in search_roots:
        recursive_matches = sorted(root.rglob(f"{default_stem}.xml"))
        if recursive_matches:
            return recursive_matches[0]
        xml_files = sorted(root.rglob("*.xml"))
        if len(xml_files) == 1:
            return xml_files[0]

    if path.suffix.lower() != ".xml":
        candidate = path.with_suffix(".xml")
    else:
        candidate = path

    if candidate.exists():
        return candidate

    return candidate


def _extract_gender_probs(data: np.ndarray) -> tuple[float | None, float | None]:
    flat = np.array(data).reshape(-1)
    if flat.size < 2:
        return None, None
    female_prob = _clamp_float(flat[0])
    male_prob = _clamp_float(flat[1])
    return female_prob, male_prob


def _extract_age_value(data: np.ndarray) -> float | None:
    flat = np.array(data).reshape(-1)
    if flat.size == 0:
        return None
    value = _clamp_float(flat[0], 0.0)
    if 0.0 <= value <= 1.5:
        value *= 100.0
    return value


def _crop_with_margin(frame: np.ndarray, bbox: dict[str, int], margin: float) -> np.ndarray:
    height, width = frame.shape[:2]
    left = int(bbox.get("left", 0))
    top = int(bbox.get("top", 0))
    right = int(bbox.get("right", 0))
    bottom = int(bbox.get("bottom", 0))

    box_width = max(1, right - left)
    box_height = max(1, bottom - top)
    pad_x = int(box_width * margin)
    pad_y = int(box_height * margin)

    x1 = max(0, left - pad_x)
    y1 = max(0, top - pad_y)
    x2 = min(width, right + pad_x)
    y2 = min(height, bottom + pad_y)

    if x2 <= x1 or y2 <= y1:
        return frame[0:0, 0:0]

    return frame[y1:y2, x1:x2].copy()


def _face_counts_from_faces(faces: Iterable["GenderFaceEstimate"]) -> dict[str, int]:
    male = female = unknown = 0
    face_count = 0
    for face in faces:
        face_count += 1
        label = normalize_gender_label(face.gender_label)
        if label == "male":
            male += 1
        elif label == "female":
            female += 1
        else:
            unknown += 1
    return {
        "faceCount": face_count,
        "maleCount": male,
        "femaleCount": female,
        "unknownGenderCount": unknown,
    }


class GenderBackend(Protocol):
    ready: bool
    source: str

    def detect(self, frame: np.ndarray) -> list["GenderFaceEstimate"]:
        ...

    def close(self) -> None:
        ...


@dataclass(slots=True)
class GenderFaceEstimate:
    bbox: dict[str, int]
    face_confidence: float
    gender_label: str
    gender_confidence: float
    age: float | None = None
    age_confidence: float | None = None
    source: str = "openvino"
    note: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["genderLabel"] = normalize_gender_label(self.gender_label)
        payload["faceConfidence"] = round(float(self.face_confidence), 4)
        payload["genderConfidence"] = round(float(self.gender_confidence), 4)
        if self.age is not None:
            payload["age"] = round(float(self.age), 2)
        if self.age_confidence is not None:
            payload["ageConfidence"] = round(float(self.age_confidence), 4)
        return payload


@dataclass(slots=True)
class GenderSceneEstimate:
    enabled: bool
    ready: bool
    updated: bool
    detected: bool
    estimate: bool
    engine: str
    model_version: str
    face_model_version: str
    frame_index: int = 0
    frame_time: float = 0.0
    fps: float = 0.0
    frame_size: tuple[int, int] | None = None
    face_count: int = 0
    male_count: int = 0
    female_count: int = 0
    unknown_gender_count: int = 0
    raw_face_count: int = 0
    raw_male_count: int = 0
    raw_female_count: int = 0
    raw_unknown_gender_count: int = 0
    average_face_confidence: float = 0.0
    average_gender_confidence: float = 0.0
    average_age: float = 0.0
    faces: list[GenderFaceEstimate] = field(default_factory=list)
    skipped_reason: str = ""
    source: str = "openvino"

    def to_payload(self) -> dict[str, Any]:
        frame_time = (
            time_iso(self.frame_time) if self.frame_time else ""
        )
        payload: dict[str, Any] = {
            "genderEnabled": bool(self.enabled),
            "genderReady": bool(self.ready),
            "genderUpdated": bool(self.updated),
            "genderDetected": bool(self.detected),
            "genderEstimate": bool(self.estimate),
            "genderEngine": self.source or self.engine,
            "genderModelVersion": self.model_version,
            "faceModelVersion": self.face_model_version,
            "frameNumber": int(self.frame_index),
            "frameTime": frame_time,
            "genderFrameSize": list(self.frame_size) if self.frame_size else None,
            "faceCount": int(self.face_count),
            "maleCount": int(self.male_count),
            "femaleCount": int(self.female_count),
            "unknownGenderCount": int(self.unknown_gender_count),
            "rawFaceCount": int(self.raw_face_count),
            "rawMaleCount": int(self.raw_male_count),
            "rawFemaleCount": int(self.raw_female_count),
            "rawUnknownGenderCount": int(self.raw_unknown_gender_count),
            "genderAverageFaceConfidence": round(float(self.average_face_confidence), 4),
            "genderAverageConfidence": round(float(self.average_gender_confidence), 4),
            "genderAverageAge": round(float(self.average_age), 2),
            "genderFaces": [face.to_payload() for face in self.faces],
            "genderEstimateLabel": "estimated",
            "genderSource": self.source,
        }
        if self.skipped_reason:
            payload["genderSkippedReason"] = self.skipped_reason
        if self.fps:
            payload["fps"] = round(float(self.fps), 2)
        return payload


def time_iso(timestamp: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class OpenVINOGenderBackend:
    """OpenVINO face detector + age/gender classifier."""

    def __init__(
        self,
        *,
        face_model_path: str | Path = FACE_MODEL_PATH,
        gender_model_path: str | Path = GENDER_MODEL_PATH,
        device: str = GENDER_DEVICE,
        min_face_confidence: float = GENDER_MIN_FACE_CONFIDENCE,
        min_gender_confidence: float = GENDER_MIN_GENDER_CONFIDENCE,
        crop_margin: float = GENDER_CROP_MARGIN,
        max_faces: int = GENDER_MAX_FACES,
    ) -> None:
        if ov is None:  # pragma: no cover - import guard
            raise RuntimeError("openvino is not installed")

        self.source = "openvino"
        self.device = str(device or "CPU").upper()
        self.min_face_confidence = max(0.0, min(1.0, float(min_face_confidence)))
        self.min_gender_confidence = max(0.0, min(1.0, float(min_gender_confidence)))
        self.crop_margin = max(0.0, min(0.5, float(crop_margin)))
        self.max_faces = max(1, int(max_faces))

        self.face_model_xml = _resolve_model_xml_path(face_model_path, "face-detection-retail-0004")
        self.gender_model_xml = _resolve_model_xml_path(
            gender_model_path,
            "age-gender-recognition-retail-0013",
        )
        if not self.face_model_xml.exists():
            raise FileNotFoundError(f"Face detection model not found: {self.face_model_xml}")
        if not self.gender_model_xml.exists():
            raise FileNotFoundError(f"Age/gender model not found: {self.gender_model_xml}")

        self._core = ov.Core()
        self._face_compiled = self._core.compile_model(self._core.read_model(str(self.face_model_xml)), device_name=self.device)
        self._gender_compiled = self._core.compile_model(self._core.read_model(str(self.gender_model_xml)), device_name=self.device)
        self._face_input_name = _port_name(self._face_compiled.inputs[0])
        self._gender_input_name = _port_name(self._gender_compiled.inputs[0])
        self._face_output_count = len(self._face_compiled.outputs)
        self._gender_output_count = len(self._gender_compiled.outputs)
        self.ready = True

    def close(self) -> None:
        return None

    def _infer_face_boxes(self, frame: np.ndarray) -> list[dict[str, int]]:
        height, width = frame.shape[:2]
        resized = cv2.resize(frame, (300, 300))
        blob = resized.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)
        infer_request = self._face_compiled.create_infer_request()
        infer_request.infer({self._face_input_name: blob})
        output = np.array(infer_request.get_output_tensor(0).data)

        detections = []
        for det in output.reshape(-1, 7):
            confidence = float(det[2])
            if confidence < self.min_face_confidence:
                continue

            left = max(0, min(width, int(det[3] * width)))
            top = max(0, min(height, int(det[4] * height)))
            right = max(0, min(width, int(det[5] * width)))
            bottom = max(0, min(height, int(det[6] * height)))

            if right <= left or bottom <= top:
                continue

            detections.append(
                {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "confidence": confidence,
                }
            )

        detections.sort(key=lambda item: item["confidence"], reverse=True)
        return detections[: self.max_faces]

    def _classify_face(self, frame: np.ndarray, bbox: dict[str, int]) -> GenderFaceEstimate:
        crop = _crop_with_margin(frame, bbox, self.crop_margin)
        if crop.size == 0:
            return GenderFaceEstimate(
                bbox=dict(bbox),
                face_confidence=float(bbox.get("confidence", 0.0)),
                gender_label="unknown",
                gender_confidence=0.0,
                source=self.source,
                note="empty crop",
            )

        resized = cv2.resize(crop, (62, 62))
        blob = resized.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)
        infer_request = self._gender_compiled.create_infer_request()
        infer_request.infer({self._gender_input_name: blob})

        age_value: float | None = None
        female_prob: float | None = None
        male_prob: float | None = None

        for index in range(self._gender_output_count):
            data = np.array(infer_request.get_output_tensor(index).data)
            shape = tuple(data.shape)
            if data.size == 1 or shape in {(1, 1, 1, 1), (1,), (1, 1)}:
                age_value = _extract_age_value(data)
            elif data.size >= 2:
                extracted_female, extracted_male = _extract_gender_probs(data)
                if extracted_female is not None and extracted_male is not None:
                    female_prob = extracted_female
                    male_prob = extracted_male

        if female_prob is None or male_prob is None:
            return GenderFaceEstimate(
                bbox=dict(bbox),
                face_confidence=float(bbox.get("confidence", 0.0)),
                gender_label="unknown",
                gender_confidence=0.0,
                age=age_value,
                source=self.source,
                note="gender output unavailable",
            )

        if male_prob >= female_prob:
            gender_label = "male"
            gender_confidence = male_prob
        else:
            gender_label = "female"
            gender_confidence = female_prob

        if gender_confidence < self.min_gender_confidence:
            gender_label = "unknown"

        return GenderFaceEstimate(
            bbox=dict(bbox),
            face_confidence=float(bbox.get("confidence", 0.0)),
            gender_label=gender_label,
            gender_confidence=float(gender_confidence),
            age=age_value,
            age_confidence=float(gender_confidence),
            source=self.source,
        )

    def detect(self, frame: np.ndarray) -> list[GenderFaceEstimate]:
        boxes = self._infer_face_boxes(frame)
        faces = [self._classify_face(frame, bbox) for bbox in boxes]
        return faces


class DeepFaceGenderBackend:
    """Fallback gender backend using DeepFace + OpenCV Haar detection."""

    def __init__(
        self,
        *,
        crop_margin: float = GENDER_CROP_MARGIN,
        min_gender_confidence: float = GENDER_MIN_GENDER_CONFIDENCE,
        max_faces: int = GENDER_MAX_FACES,
    ) -> None:
        try:  # pragma: no cover - optional dependency
            from deepface import DeepFace
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(f"DeepFace is not installed: {exc}") from exc

        self.DeepFace = DeepFace
        self.source = "deepface"
        self.crop_margin = max(0.0, min(0.5, float(crop_margin)))
        self.min_gender_confidence = max(0.0, min(1.0, float(min_gender_confidence)))
        self.max_faces = max(1, int(max_faces))
        self.ready = True
        self._cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def close(self) -> None:
        return None

    def _detect_faces(self, frame: np.ndarray) -> list[dict[str, int]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
        results: list[dict[str, int]] = []
        for (x, y, w, h) in faces[: self.max_faces]:
            results.append(
                {
                    "left": int(x),
                    "top": int(y),
                    "right": int(x + w),
                    "bottom": int(y + h),
                    "confidence": 0.5,
                }
            )
        return results

    def _classify_face(self, frame: np.ndarray, bbox: dict[str, int]) -> GenderFaceEstimate:
        crop = _crop_with_margin(frame, bbox, self.crop_margin)
        if crop.size == 0:
            return GenderFaceEstimate(
                bbox=dict(bbox),
                face_confidence=float(bbox.get("confidence", 0.0)),
                gender_label="unknown",
                gender_confidence=0.0,
                source=self.source,
                note="empty crop",
            )

        try:  # pragma: no cover - optional dependency
            result = self.DeepFace.analyze(
                crop,
                actions=("age", "gender"),
                detector_backend="skip",
                enforce_detection=False,
                silent=True,
            )
        except Exception as exc:  # pragma: no cover - optional dependency
            return GenderFaceEstimate(
                bbox=dict(bbox),
                face_confidence=float(bbox.get("confidence", 0.0)),
                gender_label="unknown",
                gender_confidence=0.0,
                source=self.source,
                note=str(exc),
            )

        if isinstance(result, list) and result:
            result = result[0]
        if not isinstance(result, dict):
            return GenderFaceEstimate(
                bbox=dict(bbox),
                face_confidence=float(bbox.get("confidence", 0.0)),
                gender_label="unknown",
                gender_confidence=0.0,
                source=self.source,
                note="unexpected DeepFace result",
            )

        dominant_gender = normalize_gender_label(result.get("dominant_gender"))
        gender_scores = result.get("gender")
        gender_confidence = 0.0
        if isinstance(gender_scores, dict):
            if dominant_gender == "male":
                gender_confidence = _clamp_float(gender_scores.get("Man") or gender_scores.get("male"), 0.0)
            elif dominant_gender == "female":
                gender_confidence = _clamp_float(gender_scores.get("Woman") or gender_scores.get("female"), 0.0)

        if gender_confidence > 1.0:
            gender_confidence /= 100.0

        if gender_confidence < self.min_gender_confidence:
            dominant_gender = "unknown"

        return GenderFaceEstimate(
            bbox=dict(bbox),
            face_confidence=float(bbox.get("confidence", 0.0)),
            gender_label=dominant_gender,
            gender_confidence=float(gender_confidence),
            age=_clamp_float(result.get("age"), 0.0) if result.get("age") is not None else None,
            age_confidence=float(gender_confidence),
            source=self.source,
        )

    def detect(self, frame: np.ndarray) -> list[GenderFaceEstimate]:
        boxes = self._detect_faces(frame)
        return [self._classify_face(frame, bbox) for bbox in boxes]


class DisabledGenderBackend:
    source = "disabled"
    ready = False

    def detect(self, frame: np.ndarray) -> list[GenderFaceEstimate]:
        return []

    def close(self) -> None:
        return None


class GenderSceneRuntime:
    """Analyze a frame every N frames and smooth scene gender counts."""

    def __init__(
        self,
        *,
        backend: GenderBackend | None = None,
        enabled: bool | None = None,
        engine: str | None = None,
        analyze_every_n_frames: int | None = None,
        smoothing_window: int | None = None,
        max_faces: int | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.logger = logger
        self.engine = (engine or GENDER_ENGINE or "disabled").strip().lower()
        self.enabled = bool(GENDER_DETECTION_ENABLED if enabled is None else enabled)
        if self.engine == "disabled":
            self.enabled = False

        self.analyze_every_n_frames = max(1, int(analyze_every_n_frames or GENDER_ANALYZE_EVERY_N_FRAMES))
        self.smoothing_window = max(1, int(smoothing_window or GENDER_SMOOTHING_WINDOW))
        self.max_faces = max(1, int(max_faces or GENDER_MAX_FACES))
        self._history: deque[dict[str, int]] = deque(maxlen=self.smoothing_window)
        self._lock = Lock()
        self._frame_counter = 0
        self._startup_error: str | None = None
        self.backend: GenderBackend | None = None

        if backend is not None:
            self.backend = backend
        else:
            self.backend = self._build_backend()

        self.ready = bool(self.backend is not None and getattr(self.backend, "ready", False))
        self._latest_summary = self._empty_summary(
            skipped_reason="gender pipeline not initialized" if self.ready else self._startup_error or "gender pipeline unavailable",
        )
        if not self.ready and self.enabled:
            self._latest_summary = self._empty_summary(
                skipped_reason=self._startup_error or "gender pipeline unavailable",
            )

    def _build_backend(self) -> GenderBackend | None:
        if not self.enabled:
            self._startup_error = "Gender detection disabled by configuration"
            _log(self.logger, self._startup_error, "WARN")
            return DisabledGenderBackend()

        if self.engine == "deepface":
            if not GENDER_USE_DEEPFACE_FALLBACK:
                self._startup_error = "DeepFace fallback disabled by configuration"
                _log(self.logger, self._startup_error, "WARN")
                return None
            try:
                backend = DeepFaceGenderBackend(max_faces=self.max_faces)
                _log(self.logger, "Gender fallback backend ready (DeepFace)", "INFO")
                return backend
            except Exception as exc:  # pragma: no cover - optional dependency
                self._startup_error = str(exc)
                _log(self.logger, self._startup_error, "WARN")
                return None

        try:
            backend = OpenVINOGenderBackend(max_faces=self.max_faces)
            _log(
                self.logger,
                f"Gender runtime ready using OpenVINO models at {backend.face_model_xml} and {backend.gender_model_xml}",
                "INFO",
            )
            return backend
        except Exception as exc:
            self._startup_error = str(exc)
            _log(self.logger, self._startup_error, "WARN")
            if not GENDER_USE_DEEPFACE_FALLBACK:
                return None
            try:
                backend = DeepFaceGenderBackend(max_faces=self.max_faces)
                _log(self.logger, "Gender fallback backend ready (DeepFace)", "WARN")
                return backend
            except Exception as fallback_exc:  # pragma: no cover - optional dependency
                self._startup_error = f"OpenVINO failed: {exc}; DeepFace fallback failed: {fallback_exc}"
                _log(self.logger, self._startup_error, "WARN")
                return None

    def _empty_summary(self, *, skipped_reason: str = "") -> GenderSceneEstimate:
        return GenderSceneEstimate(
            enabled=self.enabled,
            ready=bool(getattr(self, "ready", False)),
            updated=False,
            detected=False,
            estimate=True,
            engine=self.engine,
            model_version=GENDER_MODEL_VERSION,
            face_model_version=FACE_MODEL_VERSION,
            skipped_reason=skipped_reason,
            source=getattr(getattr(self, "backend", None), "source", self.engine),
        )

    def _smooth_counts(self, raw_counts: dict[str, int]) -> dict[str, int]:
        self._history.append(raw_counts)
        if not self._history:
            return dict(raw_counts)

        smoothed = {}
        for key in ("faceCount", "maleCount", "femaleCount", "unknownGenderCount"):
            values = [entry.get(key, 0) for entry in self._history]
            smoothed[key] = int(round(mean(values))) if values else 0
        return smoothed

    def detect(
        self,
        frame: np.ndarray,
        *,
        frame_count: int | None = None,
        fps: float | None = None,
        force: bool = False,
    ) -> GenderSceneEstimate:
        with self._lock:
            self._frame_counter += 1
            frame_index = int(frame_count if frame_count is not None else self._frame_counter)
            now = time()
            frame_size = (int(frame.shape[1]), int(frame.shape[0])) if frame is not None and frame.size else None

            if not self.enabled or self.backend is None or not getattr(self.backend, "ready", False):
                summary = self._empty_summary(
                    skipped_reason=self._startup_error or "gender pipeline unavailable",
                )
                summary.frame_index = frame_index
                summary.frame_time = now
                summary.frame_size = frame_size
                summary.fps = float(fps or 0.0)
                self._latest_summary = summary
                return summary

            should_analyze = force or frame_count is None or frame_index % self.analyze_every_n_frames == 0
            if not should_analyze and self._latest_summary is not None:
                summary = replace(
                    self._latest_summary,
                    frame_index=frame_index,
                    frame_time=now,
                    fps=float(fps or self._latest_summary.fps),
                    frame_size=frame_size,
                    updated=False,
                    skipped_reason=f"sampled every {self.analyze_every_n_frames} frames",
                )
                self._latest_summary = summary
                return summary

            faces = list(self.backend.detect(frame))[: self.max_faces]
            raw_counts = _face_counts_from_faces(faces)
            smoothed_counts = self._smooth_counts(raw_counts)
            face_confidences = [face.face_confidence for face in faces]
            gender_confidences = [face.gender_confidence for face in faces if face.gender_label != "unknown"]
            ages = [face.age for face in faces if face.age is not None]

            summary = GenderSceneEstimate(
                enabled=self.enabled,
                ready=True,
                updated=True,
                detected=raw_counts["faceCount"] > 0,
                estimate=True,
                engine=self.engine,
                model_version=GENDER_MODEL_VERSION,
                face_model_version=FACE_MODEL_VERSION,
                frame_index=frame_index,
                frame_time=now,
                fps=float(fps or 0.0),
                frame_size=frame_size,
                face_count=smoothed_counts["faceCount"],
                male_count=smoothed_counts["maleCount"],
                female_count=smoothed_counts["femaleCount"],
                unknown_gender_count=smoothed_counts["unknownGenderCount"],
                raw_face_count=raw_counts["faceCount"],
                raw_male_count=raw_counts["maleCount"],
                raw_female_count=raw_counts["femaleCount"],
                raw_unknown_gender_count=raw_counts["unknownGenderCount"],
                average_face_confidence=float(mean(face_confidences)) if face_confidences else 0.0,
                average_gender_confidence=float(mean(gender_confidences)) if gender_confidences else 0.0,
                average_age=float(mean(ages)) if ages else 0.0,
                faces=faces,
                skipped_reason="",
                source=getattr(self.backend, "source", self.engine),
            )
            self._latest_summary = summary
            return summary

    def get_latest_summary(self) -> GenderSceneEstimate:
        return self._latest_summary

    def close(self) -> None:
        try:
            if self.backend is not None:
                self.backend.close()
        except Exception:
            pass

"""
SafeStree ML runtime configuration.

Loads backend/ml/.env first, then exposes a small set of typed helpers and
feature flags so app.py and db.py do not each need their own env bootstrap.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None, override=False, *args, **kwargs):  # type: ignore[no-redef]
        """Minimal .env loader fallback when python-dotenv is not installed."""
        if dotenv_path is None:
            return False

        path = Path(dotenv_path)
        if not path.exists():
            return False

        loaded = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if not override and key in os.environ:
                continue

            os.environ[key] = value
            loaded = True

        return loaded


ML_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ML_DIR / ".env")


def env_str(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip()


def env_bool(name: str, default: str = "1") -> bool:
    value = env_str(name, default).lower()
    return value not in {"0", "false", "no", "off"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env_str(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env_str(name, str(default)))
    except ValueError:
        return default


def normalize_gender_engine(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"disabled", "off", "none", "0"}:
        return "disabled"
    if value in {"deepface", "fallback"}:
        return "deepface"
    if value in {"openvino", ""}:
        return "openvino"
    return "openvino"


def normalize_voice_engine(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"disabled", "off", "none", "0"}:
        return "disabled"
    if value in {"legacy_google", "speech_recognition", "google", "vosk", "offline_vosk", ""}:
        return "vosk"
    return "vosk"


HAND_GESTURE_ENABLED = env_bool("ENABLE_HAND_GESTURE", "1")
VOICE_ENABLED = env_bool("ENABLE_VOICE_SOS", "1")
GENDER_DETECTION_ENABLED = env_bool("ENABLE_GENDER_DETECTION", "0")

GESTURE_ENGINE = env_str("GESTURE_ENGINE", "mediapipe_landmark").lower()
GESTURE_ACTIVE_MODEL = env_str(
    "GESTURE_ACTIVE_MODEL",
    "data/models/gestures/active_model.json",
)
GESTURE_MIN_CONFIDENCE = env_float("GESTURE_MIN_CONFIDENCE", 0.80)
GESTURE_CONFIRMATION_FRAMES = env_int("GESTURE_CONFIRMATION_FRAMES", 10)
GESTURE_CONFIRMATION_WINDOW = env_int("GESTURE_CONFIRMATION_WINDOW", 12)
GESTURE_TRIGGER_LABELS = tuple(
    label.strip().upper()
    for label in env_str("GESTURE_TRIGGER_LABELS", "SOS").split(",")
    if label.strip()
)
GESTURE_TRAIN_MIN_SAMPLES_PER_CLASS = env_int("GESTURE_TRAIN_MIN_SAMPLES_PER_CLASS", 10)
GESTURE_TRAIN_RECOMMENDED_SAMPLES_PER_CLASS = env_int(
    "GESTURE_TRAIN_RECOMMENDED_SAMPLES_PER_CLASS",
    20,
)
VOICE_ENGINE = normalize_voice_engine(env_str("VOICE_ENGINE", "vosk"))
VOICE_MODEL_PATH = env_str("VOICE_MODEL_PATH", "data/models/voice/vosk-model-small-en-us")
VOICE_MODEL_VERSION = env_str("VOICE_MODEL_VERSION", "vosk_offline_v1")
VOICE_SAMPLE_RATE = env_int("VOICE_SAMPLE_RATE", 16000)
VOICE_CHUNK_SIZE = env_int("VOICE_CHUNK_SIZE", 4096)
VOICE_CONFIRMATION_HITS = env_int("VOICE_CONFIRMATION_HITS", 2)
VOICE_CONFIRMATION_WINDOW_SECONDS = env_float("VOICE_CONFIRMATION_WINDOW_SECONDS", 5.0)
VOICE_TRIGGER_COOLDOWN_SECONDS = env_float("VOICE_TRIGGER_COOLDOWN_SECONDS", 2.0)
VOICE_MATCH_THRESHOLD = env_float("VOICE_MATCH_THRESHOLD", 0.78)
VOICE_HIGH_CONFIDENCE_THRESHOLD = env_float("VOICE_HIGH_CONFIDENCE_THRESHOLD", 0.92)
VOICE_TRIGGER_PHRASES = tuple(
    phrase.strip()
    for phrase in env_str("VOICE_TRIGGER_PHRASES", "").split(",")
    if phrase.strip()
)
GENDER_ENGINE = normalize_gender_engine(env_str("GENDER_ENGINE", "disabled"))
GENDER_MODEL_PATH = env_str("GENDER_MODEL_PATH", "data/models/openvino/age-gender-recognition-retail-0013")
FACE_MODEL_PATH = env_str("FACE_MODEL_PATH", "data/models/openvino/face-detection-retail-0004")
GENDER_MODEL_VERSION = env_str("GENDER_MODEL_VERSION", "openvino_retail_0013_v1")
FACE_MODEL_VERSION = env_str("FACE_MODEL_VERSION", "openvino_face_0004_v1")
GENDER_DEVICE = env_str("GENDER_DEVICE", "CPU").upper()
GENDER_MIN_FACE_CONFIDENCE = env_float("GENDER_MIN_FACE_CONFIDENCE", 0.40)
GENDER_MIN_GENDER_CONFIDENCE = env_float("GENDER_MIN_GENDER_CONFIDENCE", 0.65)
GENDER_ANALYZE_EVERY_N_FRAMES = env_int("GENDER_ANALYZE_EVERY_N_FRAMES", 6)
GENDER_SMOOTHING_WINDOW = env_int("GENDER_SMOOTHING_WINDOW", 5)
GENDER_MAX_FACES = env_int("GENDER_MAX_FACES", 5)
GENDER_CROP_MARGIN = env_float("GENDER_CROP_MARGIN", 0.15)
GENDER_USE_DEEPFACE_FALLBACK = env_bool("GENDER_USE_DEEPFACE_FALLBACK", "1")

CAMERA_INDEX = env_int("CAMERA_INDEX", 0)
MAX_CAMERA_INDEX = env_int("MAX_CAMERA_INDEX", 8)
ENABLE_DISPLAY = env_bool("ENABLE_DISPLAY", "1")
LOCATION_CACHE_MAX_AGE_SECONDS = env_int("LOCATION_CACHE_MAX_AGE_SECONDS", 300)

ML_CAMERA_ID = env_str("ML_CAMERA_ID", "cam-main-gate-01")
ML_CAMERA_NAME = env_str("ML_CAMERA_NAME", "Main Gate CCTV")
ML_CAMERA_LOCATION_LABEL = env_str("ML_CAMERA_LOCATION_LABEL", "College Main Gate")
ML_CAMERA_LATITUDE = env_str("ML_CAMERA_LATITUDE", "")
ML_CAMERA_LONGITUDE = env_str("ML_CAMERA_LONGITUDE", "")
ML_CAMERA_ACCURACY = env_str("ML_CAMERA_ACCURACY", "")

CCTV_SOS_ENDPOINT = env_str("CCTV_SOS_ENDPOINT", "")
CCTV_API_KEY = env_str("CCTV_API_KEY", "")
CCTV_INTERNAL_ENDPOINT = env_str("CCTV_INTERNAL_ENDPOINT", "")
CCTV_INTERNAL_SERVICE_TOKEN = env_str("CCTV_INTERNAL_SERVICE_TOKEN", "")
CCTV_INTERNAL_SERVICE_NAME = env_str("CCTV_INTERNAL_SERVICE_NAME", "backend_ml")

# Phase 8 hardening
ALERT_RETRY_QUEUE_DB_PATH = env_str("ALERT_RETRY_QUEUE_DB_PATH", "data/cache/alert_retry_queue.db")
ALERT_RETRY_WORKER_INTERVAL_SECONDS = env_int("ALERT_RETRY_WORKER_INTERVAL_SECONDS", 15)
ALERT_RETRY_WORKER_BATCH_SIZE = env_int("ALERT_RETRY_WORKER_BATCH_SIZE", 5)
ALERT_DISPATCH_MAX_ATTEMPTS = env_int("ALERT_DISPATCH_MAX_ATTEMPTS", 2)
ALERT_IMAGE_RETENTION_DAYS = env_int("ALERT_IMAGE_RETENTION_DAYS", 7)
ALERT_RETENTION_SCAN_INTERVAL_SECONDS = env_int("ALERT_RETENTION_SCAN_INTERVAL_SECONDS", 300)
STARTUP_HEALTH_REPORT_PATH = env_str("STARTUP_HEALTH_REPORT_PATH", "data/cache/startup_health_report.json")
CAMERA_RECONNECT_MAX_ATTEMPTS = env_int("CAMERA_RECONNECT_MAX_ATTEMPTS", 3)

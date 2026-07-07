"""Model registry helpers for hand gesture artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import GESTURE_ACTIVE_MODEL


PIPELINE_ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = PIPELINE_ROOT / "data" / "models" / "gestures"
TRAINING_ROOT = PIPELINE_ROOT / "data" / "training_samples" / "gestures"
RAW_SESSIONS_ROOT = TRAINING_ROOT / "raw_sessions"
PROCESSED_ROOT = TRAINING_ROOT / "processed"
LOGS_ROOT = PIPELINE_ROOT / "data" / "logs"


def ensure_gesture_storage_layout() -> None:
    for path in (MODEL_ROOT, TRAINING_ROOT, RAW_SESSIONS_ROOT, PROCESSED_ROOT, LOGS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def model_id_from_time(prefix: str = "gesture_knn") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def list_model_dirs() -> list[Path]:
    ensure_gesture_storage_layout()
    required_files = ("model.joblib", "scaler.joblib", "metadata.json", "labels.json")

    model_dirs = []
    for path in MODEL_ROOT.iterdir():
        if not path.is_dir() or not path.name.startswith("gesture_knn_"):
            continue
        if all((path / filename).exists() for filename in required_files):
            model_dirs.append(path)

    return sorted(model_dirs, key=lambda path: path.stat().st_mtime)


def latest_model_dir() -> Path | None:
    model_dirs = list_model_dirs()
    return model_dirs[-1] if model_dirs else None


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)


def active_model_registry_path() -> Path:
    return PIPELINE_ROOT / GESTURE_ACTIVE_MODEL


def read_active_model_spec() -> dict[str, Any] | None:
    registry = active_model_registry_path()
    data = load_json(registry)
    if not data:
        return None
    model_path = data.get("path")
    if model_path:
        resolved = Path(model_path)
        if not resolved.is_absolute():
            resolved = PIPELINE_ROOT / resolved
        data["resolvedPath"] = str(resolved)
    return data


def resolve_active_model_dir() -> Path | None:
    spec = read_active_model_spec()
    if spec and spec.get("resolvedPath"):
        model_dir = Path(spec["resolvedPath"])
        if model_dir.exists() and model_dir.is_dir():
            return model_dir

    model_dir = latest_model_dir()
    return model_dir


def activate_model(model_dir: Path, *, model_id: str | None = None) -> Path:
    ensure_gesture_storage_layout()
    resolved_dir = model_dir.resolve()
    payload = {
        "activeModelId": model_id or resolved_dir.name,
        "path": str(resolved_dir.relative_to(PIPELINE_ROOT)),
        "activatedAt": utc_timestamp(),
    }
    registry_path = active_model_registry_path()
    save_json(registry_path, payload)
    return registry_path

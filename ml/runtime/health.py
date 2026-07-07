"""Startup health report helpers for the SafeStree ML runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


Logger = Callable[[str, str], None]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _component_state(enabled: bool, ready: bool) -> str:
    if not enabled:
        return "disabled"
    return "ready" if ready else "degraded"


def _setup_hint(component: str, *, path: str = "", command: str = "", env_var: str = "") -> str:
    parts: list[str] = []
    if path:
        parts.append(f"path={path}")
    if env_var:
        parts.append(f"set {env_var}")
    if command:
        parts.append(f"run {command}")
    joined = "; ".join(parts)
    if not joined:
        return ""
    return f"{component}: {joined}"


def _component(
    name: str,
    *,
    enabled: bool,
    ready: bool,
    message: str,
    setup_hint: str = "",
    blocking: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = _component_state(enabled, ready)
    if enabled and not ready and blocking:
        state = "blocking"
    return {
        "name": name,
        "enabled": bool(enabled),
        "ready": bool(ready or not enabled),
        "state": state,
        "blocking": bool(blocking and enabled and not ready),
        "message": message,
        "setupHint": setup_hint,
        "details": details or {},
    }


def build_startup_health_report(
    *,
    camera: dict[str, Any],
    gesture: dict[str, Any],
    voice: dict[str, Any],
    gender: dict[str, Any],
    dispatch: dict[str, Any],
    retention: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    camera_component = _component(
        "camera",
        enabled=True,
        ready=bool(camera.get("ready")),
        message=str(camera.get("message", "")),
        setup_hint=_setup_hint(
            "Camera",
            command="Verify CAMERA_INDEX / MAX_CAMERA_INDEX and reconnect the USB/RTSP source",
        ),
        blocking=True,
        details=camera,
    )
    gesture_component = _component(
        "gesture",
        enabled=bool(gesture.get("enabled", True)),
        ready=bool(gesture.get("ready")),
        message=str(gesture.get("message", "")),
        setup_hint=_setup_hint(
            "Gesture model",
            path=str(gesture.get("modelDir", "")),
            command="python scripts/train_gesture_landmarks.py --wizard --labels SOS,NEGATIVE --samples 160 --negative-samples 250",
            env_var="GESTURE_ACTIVE_MODEL / GESTURE_ENGINE",
        ),
        blocking=False,
        details=gesture,
    )
    voice_component = _component(
        "voice",
        enabled=bool(voice.get("enabled", True)),
        ready=bool(voice.get("ready")),
        message=str(voice.get("message", "")),
        setup_hint=_setup_hint(
            "Voice model",
            path=str(voice.get("modelPath", "")),
            command="python scripts/test_voice_sos.py --offline",
            env_var="VOICE_MODEL_PATH / VOICE_ENGINE",
        ),
        blocking=False,
        details=voice,
    )
    gender_component = _component(
        "gender",
        enabled=bool(gender.get("enabled", True)),
        ready=bool(gender.get("ready")),
        message=str(gender.get("message", "")),
        setup_hint=_setup_hint(
            "Gender models",
            path=f"{gender.get('faceModelPath', '')}, {gender.get('genderModelPath', '')}",
            command="python scripts/setup_gender_models.py",
            env_var="GENDER_MODEL_PATH / FACE_MODEL_PATH / GENDER_ENGINE",
        ),
        blocking=False,
        details=gender,
    )
    dispatch_component = _component(
        "dispatch",
        enabled=True,
        ready=bool(dispatch.get("ready")),
        message=str(dispatch.get("message", "")),
        setup_hint=_setup_hint(
            "Dispatch queue",
            path=str(dispatch.get("queuePath", "")),
            command="Check CCTV_INTERNAL_ENDPOINT and CCTV_INTERNAL_SERVICE_TOKEN",
        ),
        blocking=True,
        details=dispatch,
    )
    retention_component = _component(
        "retention",
        enabled=True,
        ready=True,
        message=str(retention.get("message", "")),
        details=retention,
    )

    components = [
        camera_component,
        gesture_component,
        voice_component,
        gender_component,
        dispatch_component,
        retention_component,
    ]

    blocking_components = [component for component in components if component["blocking"]]
    optional_degraded = [
        component
        for component in components
        if component["enabled"] and not component["ready"] and not component["blocking"]
    ]

    status = "healthy" if not blocking_components and not optional_degraded else "degraded"
    setup_instructions = [
        component["setupHint"]
        for component in components
        if component["setupHint"] and component["enabled"] and not component["ready"]
    ]

    return {
        "generatedAt": _utc_now_iso(),
        "status": status,
        "components": components,
        "setupInstructions": setup_instructions,
        "metrics": metrics or {},
        "notes": notes or [],
    }


def write_startup_health_report(report: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[1] / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=True)
    return path


def log_startup_health_report(report: dict[str, Any], logger: Logger | None = None) -> None:
    def emit(message: str, prefix: str = "INFO") -> None:
        if logger is None:
            print(f"[{prefix}] {message}")
        else:
            logger(message, prefix)

    emit(f"Startup health status: {report.get('status', 'unknown')}")
    for component in report.get("components", []):
        emit(
            f"Health[{component.get('name')}] state={component.get('state')} ready={component.get('ready')} "
            f"message={component.get('message', '')}",
            "INFO",
        )

    for instruction in report.get("setupInstructions", []):
        emit(instruction, "WARN")


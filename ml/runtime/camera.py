"""Camera discovery and setup helpers for the SafeStree ML runtime."""

from __future__ import annotations

import platform
import time
from typing import Callable, Iterable

import cv2


Logger = Callable[[str, str], None]


def _log(logger: Logger | None, message: str, prefix: str = "INFO") -> None:
    if logger is None:
        print(f"[{prefix}] {message}")
        return

    logger(message, prefix)


def get_camera_backends(system_name: str | None = None) -> list[tuple[str, int]]:
    system_name = (system_name or platform.system()).lower()

    if system_name == "windows":
        candidates = [
            ("CAP_DSHOW", cv2.CAP_DSHOW),
            ("CAP_MSMF", getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)),
            ("CAP_ANY", cv2.CAP_ANY),
        ]
    elif system_name == "linux":
        candidates = [
            ("CAP_V4L2", getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)),
            ("CAP_GSTREAMER", getattr(cv2, "CAP_GSTREAMER", cv2.CAP_ANY)),
            ("CAP_ANY", cv2.CAP_ANY),
        ]
    elif system_name == "darwin":
        candidates = [
            ("CAP_AVFOUNDATION", getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY)),
            ("CAP_ANY", cv2.CAP_ANY),
        ]
    else:
        candidates = [("CAP_ANY", cv2.CAP_ANY)]

    unique_candidates: list[tuple[str, int]] = []
    seen: set[int] = set()
    for backend_name, backend_id in candidates:
        if backend_id in seen:
            continue
        seen.add(backend_id)
        unique_candidates.append((backend_name, backend_id))

    return unique_candidates


def open_camera(index: int, backend_id: int) -> cv2.VideoCapture:
    if backend_id == cv2.CAP_ANY:
        return cv2.VideoCapture(index)
    return cv2.VideoCapture(index, backend_id)


def configure_camera(cap: cv2.VideoCapture, width: int = 1280, height: int = 720) -> cv2.VideoCapture:
    if cap is None:
        return cap

    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    except Exception:
        pass

    return cap


def probe_camera(cap: cv2.VideoCapture) -> bool:
    if cap is None or not cap.isOpened():
        return False

    try:
        success, frame = cap.read()
    except Exception:
        return False
    return bool(success and frame is not None)


def reconnect_camera(
    *,
    current_index: int,
    current_backend_name: str | None,
    current_backend_id: int | None,
    max_camera_index: int = 8,
    logger: Logger | None = None,
    retry_delays: Iterable[float] = (0.25, 0.5, 1.0),
) -> tuple[cv2.VideoCapture | None, int, str | None, int | None]:
    """Try to restore the camera feed without terminating the runtime."""

    backend_id = current_backend_id if current_backend_id is not None else cv2.CAP_ANY
    delays = [max(0.0, float(delay)) for delay in retry_delays]
    attempts = max(1, len(delays) + 1)

    _log(
        logger,
        f"Attempting camera reconnect from index={current_index} backend={current_backend_name or 'CAP_ANY'}",
        "WARN",
    )

    for attempt in range(attempts):
        cap = None
        cap_usable = False
        try:
            cap = open_camera(current_index, backend_id)
            cap = configure_camera(cap)
            cap_usable = probe_camera(cap)
            if cap_usable:
                _log(logger, "Camera reconnect succeeded on the active index", "INFO")
                return cap, current_index, current_backend_name, current_backend_id
        except Exception as exc:
            _log(logger, f"Reconnect attempt {attempt + 1}/{attempts} failed: {exc}", "WARN")
        finally:
            if cap is not None:
                try:
                    if not cap_usable:
                        cap.release()
                except Exception:
                    try:
                        cap.release()
                    except Exception:
                        pass

        if attempt < len(delays):
            time.sleep(delays[attempt])

    recovered_index, recovered_backend_name, recovered_backend_id = find_camera(
        max_camera_index=max_camera_index,
        logger=logger,
    )
    if recovered_index >= 0 and recovered_backend_id is not None:
        cap = open_camera(recovered_index, recovered_backend_id)
        cap = configure_camera(cap)
        if probe_camera(cap):
            _log(
                logger,
                f"Camera recovered on fallback index {recovered_index} using {recovered_backend_name}",
                "INFO",
            )
            return cap, recovered_index, recovered_backend_name, recovered_backend_id
        if cap is not None:
            cap.release()

    _log(logger, "Camera reconnect failed; continuing to retry in the background", "ERROR")
    return None, current_index, current_backend_name, current_backend_id


def find_camera(
    max_camera_index: int = 8,
    forced_camera_index: str | int | None = None,
    logger: Logger | None = None,
) -> tuple[int, str | None, int | None]:
    """Probe camera backends and return the first working index."""

    max_camera_index = max(1, int(max_camera_index))

    if forced_camera_index is not None:
        try:
            camera_indices = [int(forced_camera_index)]
        except (TypeError, ValueError):
            _log(
                logger,
                f"Invalid CAMERA_INDEX='{forced_camera_index}', falling back to 0..{max_camera_index - 1}",
                "WARN",
            )
            camera_indices = list(range(max_camera_index))
    else:
        camera_indices = list(range(max_camera_index))

    attempts: list[str] = []

    for backend_name, backend_id in get_camera_backends():
        for index in camera_indices:
            attempts.append(f"{backend_name}:{index}")
            cap = None
            try:
                cap = open_camera(index, backend_id)
                if cap.isOpened():
                    success, frame = cap.read()
                    if success and frame is not None:
                        return index, backend_name, backend_id
            except Exception:
                continue
            finally:
                if cap is not None:
                    cap.release()

    if attempts:
        preview_attempts = ", ".join(attempts[:10])
        suffix = " ..." if len(attempts) > 10 else ""
        _log(logger, f"Camera probe attempts: {preview_attempts}{suffix}", "WARN")

    return -1, None, None

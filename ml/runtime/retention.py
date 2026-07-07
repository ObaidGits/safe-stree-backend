"""Privacy-safe retention helpers for confirmed SOS alert snapshots."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Iterable


Logger = Callable[[str, str], None]


def _log(logger: Logger | None, message: str, prefix: str = "INFO") -> None:
    if logger is None:
        print(f"[{prefix}] {message}")
        return
    logger(message, prefix)


def _resolve_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = (Path(__file__).resolve().parents[1] / resolved).resolve()
    return resolved


def _normalize_protected_paths(protected_paths: Iterable[str | Path] | None) -> set[str]:
    normalized: set[str] = set()
    for item in protected_paths or ():
        try:
            normalized.add(str(Path(item).expanduser().resolve()))
        except Exception:
            normalized.add(str(item))
    return normalized


def cleanup_alert_snapshots(
    images_dir: str | Path,
    *,
    retention_days: int,
    protected_paths: Iterable[str | Path] | None = None,
    logger: Logger | None = None,
) -> dict[str, Any]:
    """Delete expired SOS snapshots unless a queued alert still needs them."""

    directory = _resolve_path(images_dir)
    directory.mkdir(parents=True, exist_ok=True)

    retention_days = max(0, int(retention_days))
    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    protected = _normalize_protected_paths(protected_paths)

    checked = 0
    deleted = 0
    protected_count = 0
    kept = 0

    for pattern in ("sos_alert_*.jpg", "sos_alert_*.jpeg", "sos_alert_*.png"):
        for path in directory.glob(pattern):
            checked += 1
            resolved = str(path.expanduser().resolve())
            if resolved in protected or path.name in protected:
                protected_count += 1
                kept += 1
                continue

            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue

            if mtime <= cutoff:
                try:
                    path.unlink(missing_ok=True)
                    deleted += 1
                    _log(logger, f"Deleted expired SOS snapshot: {path.name}", "INFO")
                except Exception as exc:
                    _log(logger, f"Failed to delete snapshot {path.name}: {exc}", "WARN")
                    kept += 1
            else:
                kept += 1

    return {
        "imagesDir": str(directory),
        "retentionDays": retention_days,
        "cutoffEpoch": cutoff,
        "checked": checked,
        "deleted": deleted,
        "kept": kept,
        "protected": protected_count,
    }


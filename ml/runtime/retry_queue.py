"""Persistent alert retry queue for confirmed SOS events.

The queue stores failed dispatch attempts on disk so a temporary API outage
does not drop a confirmed SOS alert. Items are retried with exponential
backoff until delivery succeeds.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4


Logger = Callable[[str, str], None]


def _log(logger: Logger | None, message: str, prefix: str = "INFO") -> None:
    if logger is None:
        print(f"[{prefix}] {message}")
        return
    logger(message, prefix)


def _utc_now() -> float:
    return time.time()


def _resolve_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = (Path(__file__).resolve().parents[1] / resolved).resolve()
    return resolved


def _normalize_event_id(metadata: dict[str, Any] | None, fallback_prefix: str = "retry") -> str:
    event_id = str((metadata or {}).get("eventId") or "").strip()
    if event_id:
        return event_id
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{fallback_prefix}-{stamp}-{uuid4().hex[:8]}"


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str)


@dataclass(slots=True)
class RetryQueueItem:
    event_id: str
    image_path: str
    metadata: dict[str, Any]
    attempts: int
    next_attempt_at: float
    last_error: str
    created_at: float
    updated_at: float

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "RetryQueueItem":
        metadata = {}
        try:
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except json.JSONDecodeError:
            metadata = {}

        return cls(
            event_id=str(row["event_id"]),
            image_path=str(row["image_path"]),
            metadata=metadata if isinstance(metadata, dict) else {},
            attempts=int(row["attempts"] or 0),
            next_attempt_at=float(row["next_attempt_at"] or 0.0),
            last_error=str(row["last_error"] or ""),
            created_at=float(row["created_at"] or 0.0),
            updated_at=float(row["updated_at"] or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "imagePath": self.image_path,
            "metadata": dict(self.metadata),
            "attempts": self.attempts,
            "nextAttemptAt": self.next_attempt_at,
            "lastError": self.last_error,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class PersistentAlertRetryQueue:
    """Store retryable alert dispatches in SQLite."""

    def __init__(self, db_path: str | Path, *, logger: Logger | None = None) -> None:
        self.db_path = _resolve_path(db_path)
        self.logger = logger
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_retry_queue (
                        event_id TEXT PRIMARY KEY,
                        image_path TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        next_attempt_at REAL NOT NULL DEFAULT 0,
                        last_error TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_alert_retry_queue_due
                    ON alert_retry_queue(next_attempt_at, created_at)
                    """
                )

    @staticmethod
    def _backoff_seconds(attempts: int) -> int:
        # Cap retries so a prolonged outage does not hammer the backend.
        schedule = (5, 10, 20, 40, 80, 160, 300, 600)
        index = max(0, min(max(0, attempts - 1), len(schedule) - 1))
        return schedule[index]

    def enqueue(
        self,
        image_path: str | Path,
        metadata: dict[str, Any] | None = None,
        *,
        event_id: str | None = None,
        retry_delay_seconds: int | None = None,
    ) -> RetryQueueItem:
        payload = dict(metadata or {})
        normalized_event_id = str(event_id or _normalize_event_id(payload)).strip()
        payload["eventId"] = normalized_event_id
        resolved_image_path = str(Path(image_path).expanduser().resolve())
        now = _utc_now()
        next_attempt_at = now + max(0, int(retry_delay_seconds or 0))

        with self._lock:
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT * FROM alert_retry_queue WHERE event_id = ?",
                    (normalized_event_id,),
                ).fetchone()

                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO alert_retry_queue (
                            event_id, image_path, metadata_json, attempts,
                            next_attempt_at, last_error, created_at, updated_at
                        ) VALUES (?, ?, ?, 0, ?, '', ?, ?)
                        """,
                        (
                            normalized_event_id,
                            resolved_image_path,
                            _json_dumps(payload),
                            next_attempt_at,
                            now,
                            now,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE alert_retry_queue
                        SET image_path = ?,
                            metadata_json = ?,
                            next_attempt_at = CASE
                                WHEN ? > 0 THEN ?
                                ELSE next_attempt_at
                            END,
                            updated_at = ?
                        WHERE event_id = ?
                        """,
                        (
                            resolved_image_path,
                            _json_dumps(payload),
                            next_attempt_at,
                            next_attempt_at,
                            now,
                            normalized_event_id,
                        ),
                    )

                row = connection.execute(
                    "SELECT * FROM alert_retry_queue WHERE event_id = ?",
                    (normalized_event_id,),
                ).fetchone()
                assert row is not None
                item = RetryQueueItem.from_row(row)

        _log(self.logger, f"Queued SOS retry event {item.event_id}", "WARN")
        return item

    def due_items(self, *, now: float | None = None, limit: int = 10) -> list[RetryQueueItem]:
        current_time = _utc_now() if now is None else float(now)
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM alert_retry_queue
                    WHERE next_attempt_at <= ?
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (current_time, max(1, int(limit))),
                ).fetchall()
        return [RetryQueueItem.from_row(row) for row in rows]

    def pending_count(self) -> int:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM alert_retry_queue"
                ).fetchone()
        return int(row["count"] if row is not None else 0)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN next_attempt_at <= ? THEN 1 ELSE 0 END), 0) AS due
                    FROM alert_retry_queue
                    """,
                    (_utc_now(),),
                ).fetchone()
        return {
            "pending": int(row["total"] if row is not None else 0),
            "due": int(row["due"] if row is not None else 0),
            "path": str(self.db_path),
        }

    def protected_image_paths(self) -> set[str]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT image_path FROM alert_retry_queue"
                ).fetchall()
        return {str(row["image_path"]) for row in rows if row["image_path"]}

    def mark_sent(self, event_id: str) -> None:
        if not event_id:
            return
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM alert_retry_queue WHERE event_id = ?",
                    (str(event_id),),
                )

    def mark_failed(self, event_id: str, error_message: str, *, now: float | None = None) -> RetryQueueItem | None:
        if not event_id:
            return None

        current_time = _utc_now() if now is None else float(now)
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM alert_retry_queue WHERE event_id = ?",
                    (str(event_id),),
                ).fetchone()
                if row is None:
                    return None

                item = RetryQueueItem.from_row(row)
                next_attempt = current_time + self._backoff_seconds(item.attempts + 1)
                updated_attempts = item.attempts + 1
                connection.execute(
                    """
                    UPDATE alert_retry_queue
                    SET attempts = ?,
                        next_attempt_at = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE event_id = ?
                    """,
                    (
                        updated_attempts,
                        next_attempt,
                        str(error_message)[:500],
                        current_time,
                        str(event_id),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM alert_retry_queue WHERE event_id = ?",
                    (str(event_id),),
                ).fetchone()
                assert row is not None
                return RetryQueueItem.from_row(row)

    def drain(self) -> list[RetryQueueItem]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM alert_retry_queue ORDER BY created_at ASC"
                ).fetchall()
        return [RetryQueueItem.from_row(row) for row in rows]


def queue_snapshot(queue: PersistentAlertRetryQueue | None) -> dict[str, Any]:
    if queue is None:
        return {"pending": 0, "due": 0, "path": ""}
    return queue.stats()

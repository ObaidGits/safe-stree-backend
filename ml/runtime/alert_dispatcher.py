"""Transport confirmed SOS alerts to the API backend with durable retries."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from config import (
    ALERT_DISPATCH_MAX_ATTEMPTS,
    ALERT_RETRY_QUEUE_DB_PATH,
    ALERT_RETRY_WORKER_BATCH_SIZE,
    ALERT_RETRY_WORKER_INTERVAL_SECONDS,
)
from db import send_sos_to_cctv_route

from .retry_queue import PersistentAlertRetryQueue


Logger = Callable[[str, str], None]


def _log(logger: Logger | None, message: str, prefix: str = "INFO") -> None:
    if logger is None:
        print(f"[{prefix}] {message}")
        return
    logger(message, prefix)


class AlertDispatcher:
    """Send confirmed SOS alerts and queue failures for durable retries."""

    def __init__(
        self,
        *,
        transport: Callable[..., bool] | None = None,
        logger: Logger | None = None,
        max_attempts: int | None = None,
        retry_delays: tuple[int, ...] = (2, 4, 8, 16),
        retry_queue_path: str | None = None,
        retry_worker_interval_seconds: int | None = None,
        retry_batch_size: int | None = None,
        start_worker: bool = True,
    ) -> None:
        self.transport = transport or send_sos_to_cctv_route
        self.logger = logger
        self.max_attempts = max(1, int(max_attempts or ALERT_DISPATCH_MAX_ATTEMPTS))
        self.retry_delays = tuple(max(0, int(delay)) for delay in retry_delays)
        self.retry_queue = PersistentAlertRetryQueue(
            retry_queue_path or ALERT_RETRY_QUEUE_DB_PATH,
            logger=logger,
        )
        self.retry_worker_interval_seconds = max(
            1,
            int(retry_worker_interval_seconds or ALERT_RETRY_WORKER_INTERVAL_SECONDS),
        )
        self.retry_batch_size = max(1, int(retry_batch_size or ALERT_RETRY_WORKER_BATCH_SIZE))
        self._retry_worker_stop = threading.Event()
        self._retry_worker_thread: threading.Thread | None = None
        if start_worker:
            self.start_retry_worker()

    def _deliver_once(
        self,
        image_path: str,
        alert_payload: dict[str, Any] | None = None,
        *,
        queue_on_failure: bool = True,
    ) -> tuple[bool, str]:
        if not image_path:
            message = "No image path provided for SOS dispatch"
            _log(self.logger, message, "ERROR")
            return False, message

        payload = dict(alert_payload or {})
        event_id = str(payload.get("eventId") or "").strip()
        last_error = ""

        for attempt in range(1, self.max_attempts + 1):
            try:
                _log(
                    self.logger,
                    f"Dispatching SOS alert attempt {attempt}/{self.max_attempts} for {event_id or 'unknown-event'}",
                    "ALERT",
                )
                success = self.transport(image_path=image_path, metadata=payload)
                if success:
                    if event_id:
                        self.retry_queue.mark_sent(event_id)
                    _log(self.logger, "SOS alert dispatch completed", "ALERT")
                    return True, ""

                last_error = f"transport returned failure on attempt {attempt}/{self.max_attempts}"
                _log(self.logger, last_error, "WARN")
            except Exception as exc:  # pragma: no cover - transport specific
                last_error = str(exc)
                _log(self.logger, f"SOS alert dispatch error: {exc}", "ERROR")

            if attempt < self.max_attempts and attempt - 1 < len(self.retry_delays):
                delay = self.retry_delays[attempt - 1]
                if delay > 0:
                    time.sleep(delay)

        if queue_on_failure:
            queued_item = self.retry_queue.enqueue(
                image_path=image_path,
                metadata=payload,
                event_id=event_id or None,
            )
            self.retry_queue.mark_failed(queued_item.event_id, last_error or "dispatch failed")
            _log(
                self.logger,
                f"Queued SOS retry for event {queued_item.event_id} after dispatch failure",
                "WARN",
            )

        return False, last_error

    def dispatch(self, image_path: str, alert_payload: dict[str, Any] | None = None) -> bool:
        success, _ = self._deliver_once(image_path, alert_payload, queue_on_failure=True)
        return success

    def dispatch_async(self, image_path: str, alert_payload: dict[str, Any] | None = None) -> threading.Thread:
        worker = threading.Thread(
            target=self.dispatch,
            args=(image_path, alert_payload),
            daemon=True,
            name="sos-alert-dispatcher",
        )
        worker.start()
        return worker

    def process_retry_queue_once(self) -> int:
        items = self.retry_queue.due_items(limit=self.retry_batch_size)
        if not items:
            return 0

        processed = 0
        for item in items:
            try:
                success, error_message = self._deliver_once(
                    item.image_path,
                    item.metadata,
                    queue_on_failure=False,
                )
                if success:
                    self.retry_queue.mark_sent(item.event_id)
                else:
                    self.retry_queue.mark_failed(item.event_id, error_message or "retry failed")
                processed += 1
            except Exception as exc:  # pragma: no cover - defensive
                self.retry_queue.mark_failed(item.event_id, str(exc))
                processed += 1
        return processed

    def _retry_worker_loop(self) -> None:
        _log(self.logger, "Alert retry worker started", "INFO")
        while not self._retry_worker_stop.is_set():
            try:
                processed = self.process_retry_queue_once()
                wait_seconds = 1 if processed else self.retry_worker_interval_seconds
            except Exception as exc:  # pragma: no cover - defensive
                _log(self.logger, f"Retry worker error: {exc}", "ERROR")
                wait_seconds = self.retry_worker_interval_seconds
            self._retry_worker_stop.wait(wait_seconds)
        _log(self.logger, "Alert retry worker stopped", "INFO")

    def start_retry_worker(self) -> None:
        if self._retry_worker_thread is not None and self._retry_worker_thread.is_alive():
            return
        self._retry_worker_stop.clear()
        self._retry_worker_thread = threading.Thread(
            target=self._retry_worker_loop,
            daemon=True,
            name="sos-alert-retry-worker",
        )
        self._retry_worker_thread.start()

    def stop(self) -> None:
        self._retry_worker_stop.set()
        if self._retry_worker_thread is not None and self._retry_worker_thread.is_alive():
            self._retry_worker_thread.join(timeout=2)

    def protected_image_paths(self) -> set[str]:
        return self.retry_queue.protected_image_paths()

    def queue_stats(self) -> dict[str, Any]:
        return self.retry_queue.stats()


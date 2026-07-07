from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

try:  # pragma: no cover - environment specific
    import cv2  # type: ignore
except Exception:  # pragma: no cover - allow tests to run without OpenCV installed
    fake_cv2 = ModuleType("cv2")
    fake_cv2.CAP_ANY = 0
    fake_cv2.CAP_DSHOW = 700
    fake_cv2.CAP_MSMF = 1400
    fake_cv2.CAP_V4L2 = 200
    fake_cv2.CAP_GSTREAMER = 1800
    fake_cv2.WND_PROP_VISIBLE = 0

    class _DummyVideoCapture:
        def __init__(self, *args, **kwargs):
            self._opened = True

        def isOpened(self) -> bool:
            return self._opened

        def read(self):
            return False, None

        def release(self) -> None:
            self._opened = False

        def set(self, *args, **kwargs):
            return True

    fake_cv2.VideoCapture = _DummyVideoCapture
    fake_cv2.namedWindow = lambda *args, **kwargs: None
    fake_cv2.resizeWindow = lambda *args, **kwargs: None
    fake_cv2.imshow = lambda *args, **kwargs: None
    fake_cv2.waitKey = lambda *args, **kwargs: 255
    fake_cv2.getWindowProperty = lambda *args, **kwargs: 1
    fake_cv2.destroyAllWindows = lambda *args, **kwargs: None
    fake_cv2.flip = lambda frame, mode: frame
    fake_cv2.putText = lambda *args, **kwargs: None
    sys.modules["cv2"] = fake_cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.alert_dispatcher import AlertDispatcher
from runtime.camera import reconnect_camera
from runtime.health import build_startup_health_report, write_startup_health_report
from runtime.retention import cleanup_alert_snapshots
from runtime.retry_queue import PersistentAlertRetryQueue


class FakeCap:
    def __init__(self, *, opened: bool = True, read_success: bool = False) -> None:
        self._opened = opened
        self.read_success = read_success
        self.released = False

    def isOpened(self) -> bool:
        return self._opened and not self.released

    def read(self):
        return self.read_success, object() if self.read_success else None

    def release(self) -> None:
        self.released = True


class Phase8HardeningTests(unittest.TestCase):
    def test_retry_queue_persists_and_reschedules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            queue = PersistentAlertRetryQueue(Path(tmpdir) / "queue.db")
            image_path = Path(tmpdir) / "snapshot.jpg"
            image_path.write_bytes(b"test-image")

            item = queue.enqueue(image_path, {"eventId": "evt-1", "cameraId": "cam-1"})
            self.assertEqual(queue.pending_count(), 1)
            self.assertEqual(queue.due_items(limit=10)[0].event_id, "evt-1")

            failed = queue.mark_failed(item.event_id, "backend unavailable", now=1000.0)
            self.assertIsNotNone(failed)
            self.assertGreaterEqual(failed.next_attempt_at, 1005.0)
            self.assertEqual(queue.due_items(now=1000.0, limit=10), [])
            self.assertEqual(queue.due_items(now=2000.0, limit=10)[0].event_id, "evt-1")

            queue.mark_sent(item.event_id)
            self.assertEqual(queue.pending_count(), 0)

    def test_dispatcher_replays_queued_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.db"
            image_path = Path(tmpdir) / "snapshot.jpg"
            image_path.write_bytes(b"dispatch-image")

            attempts: list[str] = []

            def flaky_transport(*, image_path: str, metadata: dict[str, object] | None = None) -> bool:
                attempts.append(image_path)
                return len(attempts) > 1

            dispatcher = AlertDispatcher(
                transport=flaky_transport,
                retry_queue_path=str(queue_path),
                start_worker=False,
                max_attempts=1,
            )

            try:
                self.assertFalse(dispatcher.dispatch(str(image_path), {"eventId": "evt-2"}))
                self.assertEqual(dispatcher.queue_stats()["pending"], 1)

                dispatcher.retry_queue.mark_failed("evt-2", "force retry for test", now=time.time() - 100)
                processed = dispatcher.process_retry_queue_once()
                self.assertEqual(processed, 1)
                self.assertEqual(dispatcher.queue_stats()["pending"], 0)
                self.assertGreaterEqual(len(attempts), 2)
            finally:
                dispatcher.stop()

    def test_health_report_and_retention_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            images_dir = Path(tmpdir) / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            old_file = images_dir / "sos_alert_20250101_000000.jpg"
            protected_file = images_dir / "sos_alert_20250102_000000.jpg"
            recent_file = images_dir / "sos_alert_20250103_000000.jpg"
            old_file.write_bytes(b"old")
            protected_file.write_bytes(b"protected")
            recent_file.write_bytes(b"recent")

            past = time.time() - (10 * 24 * 60 * 60)
            current = time.time()
            os.utime(old_file, (past, past))
            os.utime(protected_file, (past, past))
            os.utime(recent_file, (current, current))

            retention = cleanup_alert_snapshots(
                images_dir,
                retention_days=7,
                protected_paths=[protected_file],
            )
            self.assertEqual(retention["deleted"], 1)
            self.assertTrue(protected_file.exists())
            self.assertFalse(old_file.exists())
            self.assertTrue(recent_file.exists())

            report = build_startup_health_report(
                camera={"ready": True, "index": 0, "message": "Camera ready"},
                gesture={"enabled": True, "ready": True, "message": "Gesture ready"},
                voice={"enabled": True, "ready": False, "message": "Voice missing"},
                gender={"enabled": False, "ready": False, "message": "Disabled"},
                dispatch={"ready": True, "queuePath": str(Path(tmpdir) / "queue.db"), "message": "Queue ready"},
                retention={"message": "Retention active"},
                metrics={"fps": 12.5},
            )
            report_path = write_startup_health_report(report, Path(tmpdir) / "health.json")

            self.assertEqual(report["status"], "degraded")
            self.assertTrue(report["setupInstructions"])
            self.assertTrue(report_path.exists())

    def test_camera_reconnect_falls_back_to_probe(self) -> None:
        current_cap = FakeCap(opened=True, read_success=False)
        fallback_cap = FakeCap(opened=True, read_success=True)

        def fake_open_camera(index: int, backend_id: int):
            return current_cap if index == 0 else fallback_cap

        def fake_find_camera(*, max_camera_index: int = 8, forced_camera_index=None, logger=None):
            return 1, "CAP_ANY", 0

        with patch("runtime.camera.open_camera", side_effect=fake_open_camera), patch(
            "runtime.camera.find_camera",
            side_effect=fake_find_camera,
        ), patch("runtime.camera.configure_camera", side_effect=lambda cap, width=1280, height=720: cap):
            cap, index, backend_name, backend_id = reconnect_camera(
                current_index=0,
                current_backend_name="CAP_ANY",
                current_backend_id=0,
                max_camera_index=8,
            )

        self.assertIsNotNone(cap)
        self.assertEqual(index, 1)
        self.assertEqual(backend_name, "CAP_ANY")
        self.assertEqual(backend_id, 0)


if __name__ == "__main__":
    unittest.main()

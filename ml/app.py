"""
Women's Safety System - Main Application
Monitors for SOS gestures and voice commands to trigger alerts
"""

import cv2
import copy
import time
import threading
import sys
import os
from collections import deque
from datetime import datetime
from pathlib import Path

from config import (
    ALERT_IMAGE_RETENTION_DAYS,
    ALERT_RETENTION_SCAN_INTERVAL_SECONDS,
    ALERT_DISPATCH_MAX_ATTEMPTS,
    ALERT_RETRY_WORKER_BATCH_SIZE,
    ALERT_RETRY_WORKER_INTERVAL_SECONDS,
    ENABLE_DISPLAY as CONFIG_ENABLE_DISPLAY,
    GENDER_DETECTION_ENABLED,
    GENDER_ENGINE,
    GENDER_MODEL_PATH,
    FACE_MODEL_PATH,
    GESTURE_ENGINE,
    GESTURE_CONFIRMATION_FRAMES,
    GESTURE_CONFIRMATION_WINDOW,
    GESTURE_MIN_CONFIDENCE,
    HAND_GESTURE_ENABLED,
    ML_CAMERA_ID,
    ML_CAMERA_LOCATION_LABEL,
    ML_CAMERA_NAME,
    MAX_CAMERA_INDEX as CONFIG_MAX_CAMERA_INDEX,
    VOICE_ENABLED,
    VOICE_ENGINE,
    STARTUP_HEALTH_REPORT_PATH,
)
from runtime.alert_dispatcher import AlertDispatcher
from runtime.camera import configure_camera, find_camera, open_camera
from runtime.camera import reconnect_camera
from runtime.event_aggregator import SOSEventAggregator
from runtime.health import build_startup_health_report, log_startup_health_report, write_startup_health_report
from runtime.retention import cleanup_alert_snapshots

def print_startup(message, prefix="INFO"):
    """Print startup message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{prefix}] {message}")
    sys.stdout.flush()


# ============================================================
# STARTUP
# ============================================================
print("\n" + "=" * 60)
print_startup("Women's Safety System - Starting Up", "SYSTEM")
print("=" * 60 + "\n")

print_startup(f"Python {sys.version.split()[0]}")
print_startup(f"Working Directory: {sys.path[0]}")
print()

# ============================================================
# IMPORT MODULES
# ============================================================
print_startup("Loading core modules...")

print_startup(
    "Feature flags: "
    f"hand={HAND_GESTURE_ENABLED}, "
    f"voice={VOICE_ENABLED}, "
    f"gender={GENDER_DETECTION_ENABLED}"
)
print_startup(
    "Engines: "
    f"gesture={GESTURE_ENGINE}, "
    f"voice={VOICE_ENGINE}, "
    f"gender={GENDER_ENGINE}"
)

active_gesture_engine = GESTURE_ENGINE
detect_gesture = None
detect_sos_stable = None
gesture_runtime_summary = {}
active_gender_engine = "disabled"
gender_runtime = None
if HAND_GESTURE_ENABLED:
    if GESTURE_ENGINE == "mediapipe_landmark":
        print_startup("Loading MediaPipe landmark gesture runtime...")
        try:
            from pipelines.hand_gesture import detect_gesture as detect_landmark_gesture
            from pipelines.hand_gesture import detect_sos_stable as detect_landmark_sos
            from pipelines.hand_gesture import get_runtime_summary, is_runtime_ready

            gesture_runtime_summary = get_runtime_summary()
            if is_runtime_ready():
                detect_gesture = detect_landmark_gesture
                detect_sos_stable = detect_landmark_sos
                active_gesture_engine = "mediapipe_landmark"
                print_startup("✓ Gesture detection module loaded (MediaPipe landmark)")
                print_startup(
                    "Gesture runtime: "
                    f"model={gesture_runtime_summary.get('modelId', 'unknown')}, "
                    f"labels={gesture_runtime_summary.get('labels', [])}, "
                    f"min_confidence={gesture_runtime_summary.get('minConfidence', GESTURE_MIN_CONFIDENCE):.2f}, "
                    f"confirmation={gesture_runtime_summary.get('confirmationFrames', GESTURE_CONFIRMATION_FRAMES)}/"
                    f"{gesture_runtime_summary.get('confirmationWindow', GESTURE_CONFIRMATION_WINDOW)}"
                )
            else:
                print_startup(
                    "MediaPipe gesture runtime is not ready yet. Falling back to legacy_opencv.",
                    "WARN",
                )
                from sos_gesture.gesture_detector import detect_sos_stable as legacy_detect_sos_stable

                detect_sos_stable = legacy_detect_sos_stable
                active_gesture_engine = "legacy_opencv"
                print_startup("✓ Gesture detection module loaded (OpenCV fallback)")
        except ImportError as e:
            print_startup(f"✗ Failed to load MediaPipe gesture runtime: {e}", "ERROR")
            sys.exit(1)
    else:
        if GESTURE_ENGINE != "legacy_opencv":
            print_startup(
                f"GESTURE_ENGINE='{GESTURE_ENGINE}' is not recognized. "
                "Falling back to legacy_opencv.",
                "WARN",
            )
        try:
            from sos_gesture.gesture_detector import detect_sos_stable as legacy_detect_sos_stable

            detect_sos_stable = legacy_detect_sos_stable
            active_gesture_engine = "legacy_opencv"
            print_startup("✓ Gesture detection module loaded (OpenCV fallback)")
        except ImportError as e:
            print_startup(f"✗ Failed to load gesture module: {e}", "ERROR")
            sys.exit(1)
else:
    print_startup("Hand gesture detection disabled via ENABLE_HAND_GESTURE=0", "WARN")

VoiceSOSTrigger = None
active_voice_engine = "disabled"
if VOICE_ENABLED:
    try:
        from sos_voice.voice import VoiceSOSTrigger
        active_voice_engine = VOICE_ENGINE
        print_startup("✓ Voice detection module loaded (Vosk offline)")
    except ImportError as e:
        print_startup(f"Voice module unavailable, continuing without voice: {e}", "WARN")
else:
    print_startup("Voice detection disabled via ENABLE_VOICE_SOS=0", "WARN")

if GENDER_DETECTION_ENABLED:
    print_startup("Loading gender scene runtime...")
    try:
        from pipelines.gender_detection import GenderSceneRuntime

        gender_runtime = GenderSceneRuntime(logger=print_startup)
        if gender_runtime.ready:
            active_gender_engine = getattr(gender_runtime.backend, "source", GENDER_ENGINE)
            print_startup("✓ Gender detection module loaded")
            print_startup(
                "Gender runtime: "
                f"engine={active_gender_engine}, "
                f"face_model={FACE_MODEL_PATH}, "
                f"gender_model={GENDER_MODEL_PATH}"
            )
        else:
            active_gender_engine = "disabled"
            print_startup("Gender pipeline unavailable; continuing without estimates", "WARN")
    except ImportError as e:
        print_startup(f"Gender module unavailable, continuing without gender: {e}", "WARN")
else:
    print_startup("Gender detection disabled via ENABLE_GENDER_DETECTION=0", "WARN")

try:
    from db import send_sos_to_cctv_route
    print_startup("✓ Database module loaded")
except ImportError as e:
    print_startup(f"✗ Failed to load database module: {e}", "ERROR")
    sys.exit(1)

try:
    from get_location.geolocate import get_browser_location
    from location_cache import init_db, save_location
    print_startup("✓ Location modules loaded")
except ImportError as e:
    print_startup(f"✗ Failed to load location modules: {e}", "ERROR")
    sys.exit(1)

print()

# ============================================================
# INITIALIZE SERVICES
# ============================================================
print_startup("Initializing services...")

# Location Service
try:
    init_db()
    print_startup("✓ Location database initialized")
    
    def fetch_location_background():
        try:
            location = get_browser_location()
            if location:
                save_location(
                    location["latitude"],
                    location["longitude"],
                    location.get("accuracy", 0)
                )
                print_startup("Location cached successfully")
        except Exception as e:
            print_startup(f"Location fetch failed: {e}", "WARN")
    
    threading.Thread(target=fetch_location_background, daemon=True).start()
    print_startup("✓ Location service started")
except Exception as e:
    print_startup(f"Location service error: {e}", "WARN")

# Voice Listener
voice_sos = None
if VOICE_ENABLED and VoiceSOSTrigger is not None:
    try:
        voice_sos = VoiceSOSTrigger(logger=print_startup)
        if voice_sos.start_listening():
            print_startup("✓ Voice listener started (Vosk offline)")
            active_voice_engine = "vosk"
        else:
            active_voice_engine = "disabled"
            print_startup("Voice listener unavailable; continuing without voice", "WARN")
    except Exception as e:
        print_startup(f"Voice listener error: {e}", "WARN")
else:
    print_startup("Voice listener disabled", "WARN")

print()

# ============================================================
# CAMERA SETUP
# ============================================================
print_startup("Initializing camera...")
COOLDOWN_SECONDS = 6
event_aggregator = SOSEventAggregator(
    camera_id=ML_CAMERA_ID,
    camera_name=ML_CAMERA_NAME,
    camera_location_label=ML_CAMERA_LOCATION_LABEL,
    cooldown_seconds=COOLDOWN_SECONDS,
    enable_combined_trigger=False,
    model_versions={
        "gesture": active_gesture_engine,
        "voice": active_voice_engine,
        "gender": active_gender_engine,
    },
)
alert_dispatcher = AlertDispatcher(
    logger=print_startup,
    max_attempts=ALERT_DISPATCH_MAX_ATTEMPTS,
    retry_worker_interval_seconds=ALERT_RETRY_WORKER_INTERVAL_SECONDS,
    retry_batch_size=ALERT_RETRY_WORKER_BATCH_SIZE,
    start_worker=True,
)

camera_index, camera_backend_name, camera_backend = find_camera(
    max_camera_index=CONFIG_MAX_CAMERA_INDEX,
    forced_camera_index=os.environ.get("CAMERA_INDEX"),
    logger=print_startup,
)

if camera_index == -1:
    print_startup("No camera detected at startup; monitoring will keep retrying in the background", "WARN")
    cap = None
    camera_backend_name = None
    camera_backend = None
else:
    print_startup(f"Camera found at index {camera_index} using {camera_backend_name}")

    # Open camera
    cap = open_camera(camera_index, camera_backend)

    if not cap.isOpened():
        print_startup("Failed to open camera, trying reconnect helper before continuing", "WARN")
        cap, camera_index, camera_backend_name, camera_backend = reconnect_camera(
            current_index=camera_index,
            current_backend_name=camera_backend_name,
            current_backend_id=camera_backend,
            max_camera_index=CONFIG_MAX_CAMERA_INDEX,
            logger=print_startup,
        )

# Configure camera
if cap is not None and cap.isOpened():
    cap = configure_camera(cap)

display_enabled = CONFIG_ENABLE_DISPLAY
window_name = "Women's Safety System"

if display_enabled:
    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)
    except cv2.error as e:
        display_enabled = False
        print_startup(
            f"Display unavailable ({e}). Running in headless mode.",
            "WARN",
        )

camera_ready = bool(cap is not None and cap.isOpened())
if camera_ready:
    print_startup("✓ Camera initialized")
else:
    print_startup("Camera is not ready yet; reconnect loop will keep trying", "WARN")

startup_retention = cleanup_alert_snapshots(
    Path(__file__).resolve().parent / "data" / "images",
    retention_days=ALERT_IMAGE_RETENTION_DAYS,
    protected_paths=alert_dispatcher.protected_image_paths(),
    logger=print_startup,
)
print_startup(
    f"Snapshot retention sweep complete: checked={startup_retention['checked']} "
    f"deleted={startup_retention['deleted']} protected={startup_retention['protected']}",
    "INFO",
)

startup_health_report = build_startup_health_report(
    camera={
        "ready": camera_ready,
        "index": camera_index,
        "backendName": camera_backend_name or "",
        "backendId": camera_backend if camera_backend is not None else -1,
        "message": "Camera ready" if camera_ready else "Camera not ready at startup",
    },
    gesture={
        "enabled": HAND_GESTURE_ENABLED,
        "ready": detect_sos_stable is not None,
        "engine": active_gesture_engine,
        "modelId": gesture_runtime_summary.get("modelId", ""),
        "modelDir": gesture_runtime_summary.get("modelDir", ""),
        "message": (
            f"Gesture engine={active_gesture_engine} ready"
            if detect_sos_stable is not None
            else "Gesture runtime unavailable"
        ),
    },
    voice={
        "enabled": VOICE_ENABLED,
        "ready": bool(voice_sos is not None and voice_sos.is_ready()),
        "engine": active_voice_engine,
        "modelPath": str(getattr(voice_sos, "model_path", "")),
        "message": "Voice listener ready" if voice_sos is not None and voice_sos.is_ready() else "Voice listener not ready",
    },
    gender={
        "enabled": GENDER_DETECTION_ENABLED,
        "ready": bool(gender_runtime is not None and gender_runtime.ready),
        "engine": active_gender_engine,
        "modelPath": GENDER_MODEL_PATH,
        "faceModelPath": FACE_MODEL_PATH,
        "message": "Gender runtime ready" if gender_runtime is not None and gender_runtime.ready else "Gender runtime unavailable",
    },
    dispatch={
        "ready": bool(getattr(alert_dispatcher, "retry_queue", None)),
        "queuePath": str(getattr(alert_dispatcher.retry_queue, "db_path", "")),
        "pendingCount": alert_dispatcher.queue_stats().get("pending", 0),
        "message": "Dispatch queue ready" if getattr(alert_dispatcher, "retry_queue", None) else "Dispatch queue unavailable",
    },
    retention={
        "message": f"Alert snapshot retention set to {ALERT_IMAGE_RETENTION_DAYS} days",
        "retentionDays": ALERT_IMAGE_RETENTION_DAYS,
        "checked": startup_retention["checked"],
        "deleted": startup_retention["deleted"],
    },
    metrics={
        "retentionSweep": startup_retention,
        "queue": alert_dispatcher.queue_stats(),
    },
    notes=[
        "Confirmed alerts are queued durably before retry attempts.",
        "Snapshot retention skips queued alert images.",
    ],
)
startup_health_path = write_startup_health_report(startup_health_report, STARTUP_HEALTH_REPORT_PATH)
log_startup_health_report(startup_health_report, logger=print_startup)
print_startup(f"Startup health report saved: {startup_health_path}", "INFO")
print()


# ============================================================
# MAIN MONITORING LOOP
# ============================================================
print("=" * 60)
print_startup("SYSTEM ACTIVE - Monitoring Started", "SYSTEM")
print("=" * 60)
print_startup("Press 'q' to quit")
print()

try:
    frame_count = 0
    last_frame_time = time.time()
    gesture_initialized = False
    gender_initialized = False
    sos_active = False
    camera_failure_count = 0
    last_retention_scan_at = time.time()
    last_metrics_log_at = time.time()
    frame_fps_samples = deque(maxlen=60)
    frame_latency_samples = deque(maxlen=60)

    print_startup("Entering main monitoring loop...")

    while True:
        # Check if camera is still open
        if cap is None or not cap.isOpened():
            print_startup("Camera connection lost - attempting to reconnect...", "WARN")
            cap, camera_index, camera_backend_name, camera_backend = reconnect_camera(
                current_index=camera_index,
                current_backend_name=camera_backend_name,
                current_backend_id=camera_backend,
                max_camera_index=CONFIG_MAX_CAMERA_INDEX,
                logger=print_startup,
            )
            if cap is None or not cap.isOpened():
                camera_failure_count += 1
                print_startup(
                    f"Camera reconnect still pending (attempt {camera_failure_count})",
                    "WARN",
                )
                time.sleep(1)
                continue
            camera_failure_count = 0
            print_startup("Camera reconnected successfully", "INFO")
        
        # Read frame
        success, frame = cap.read()
        if not success:
            print_startup("Failed to read frame - retrying...", "WARN")
            camera_failure_count += 1
            if camera_failure_count >= CAMERA_RECONNECT_MAX_ATTEMPTS:
                cap, camera_index, camera_backend_name, camera_backend = reconnect_camera(
                    current_index=camera_index,
                    current_backend_name=camera_backend_name,
                    current_backend_id=camera_backend,
                    max_camera_index=CONFIG_MAX_CAMERA_INDEX,
                    logger=print_startup,
                )
                camera_failure_count = 0 if cap is not None and cap.isOpened() else camera_failure_count
            time.sleep(0.1)
            continue
        camera_failure_count = 0
        
        # Flip frame horizontally for mirror effect
        frame = cv2.flip(frame, 1)
        display_frame = copy.deepcopy(frame)
        
        loop_started_at = time.perf_counter()
        current_time = time.time()
        frame_count += 1
        
        # Track FPS
        fps = 1.0 / (current_time - last_frame_time) if (current_time - last_frame_time) > 0 else 0
        last_frame_time = current_time
        frame_fps_samples.append(fps)
        
        # ---- Detect SOS Gestures ----
        gesture_detected = False
        gesture_confidence = 0.0
        gesture_label = ""
        gesture_result = None

        if HAND_GESTURE_ENABLED and detect_sos_stable is not None:
            try:
                if active_gesture_engine == "mediapipe_landmark" and detect_gesture is not None:
                    gesture_result = detect_gesture(frame, fps=fps)
                    gesture_detected = bool(gesture_result.confirmed)
                    gesture_confidence = float(gesture_result.confidence)
                    gesture_label = str(gesture_result.label or "")
                else:
                    gesture_detected, gesture_confidence = detect_sos_stable(frame, fps=fps)
                    gesture_label = "SOS" if gesture_detected else ""
                if not gesture_initialized:
                    gesture_initialized = True
                    print_startup("✓ Gesture detection initialized", "INFO")
            except Exception as e:
                print_startup(f"Gesture detection error: {e}", "ERROR")
                # Continue monitoring even if gesture detection fails
        
        # ---- Check Voice SOS ----
        voice_detected = False
        voice_confidence = 0.0
        voice_event = None
        try:
            voice_event = voice_sos.pop_triggered_event() if voice_sos else None
            if voice_event:
                voice_detected = True
                voice_confidence = float(voice_event.get("voiceConfidence", voice_event.get("confidence", 0.0)))
        except Exception as e:
            print_startup(f"Voice detection error: {e}", "ERROR")

        # ---- Scene Gender Estimate ----
        gender_scene = None
        if GENDER_DETECTION_ENABLED and gender_runtime is not None:
            try:
                gender_scene = gender_runtime.detect(frame, frame_count=frame_count, fps=fps)
                if gender_scene is not None and gender_scene.ready and not gender_initialized:
                    gender_initialized = True
                    print_startup("✓ Gender detection initialized", "INFO")
            except Exception as e:
                print_startup(f"Gender detection error: {e}", "ERROR")

        decision = event_aggregator.evaluate(
            current_time=current_time,
            hand_detected=gesture_detected,
            hand_confidence=gesture_confidence,
            voice_detected=voice_detected,
            voice_confidence=voice_confidence,
            gender_context=gender_scene.to_payload() if gender_scene is not None else None,
            frame_count=frame_count,
            fps=fps,
        )

        if decision.should_trigger:
            sos_active = True

            # Save alert image to organized directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_dir = Path(__file__).resolve().parent / "data" / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / f"sos_alert_{timestamp}.jpg"
            image_saved = cv2.imwrite(str(image_path), frame)

            if not image_saved:
                print_startup("Failed to save SOS image. Alert not dispatched.", "ERROR")
                event_aggregator.reset_cooldown()
                sos_active = False
                continue

            print()
            print_startup(f"🚨 SOS TRIGGERED: {decision.trigger_reason}", "ALERT")
            print_startup(f"Image saved: {image_path}", "ALERT")
            print_startup(f"Alert ID: {decision.event_id}", "ALERT")
            if gesture_result is not None:
                print_startup(
                    f"Gesture label: {gesture_result.label or 'unknown'} | "
                    f"raw={gesture_result.raw_confidence:.2f} | "
                    f"quality={gesture_result.quality_score:.2f} | "
                    f"window={gesture_result.positive_count}/{gesture_result.window_count}",
                    "ALERT",
                )
            print()

            if gesture_result is not None:
                decision.payload["gestureLabel"] = gesture_result.label or ""
                decision.payload["gestureRawConfidence"] = round(float(gesture_result.raw_confidence), 4)
                decision.payload["gestureQualityScore"] = round(float(gesture_result.quality_score), 4)
                decision.payload["gestureWindowCount"] = int(gesture_result.window_count)
                decision.payload["gesturePositiveCount"] = int(gesture_result.positive_count)
                decision.payload["gestureModelId"] = gesture_result.model_id
                decision.payload["gestureModelDir"] = gesture_result.model_dir
                decision.payload["gestureEngine"] = gesture_result.engine
                decision.payload["gestureClassifier"] = gesture_result.classifier

            if voice_event is not None:
                decision.payload["voiceEventId"] = voice_event.get("eventId")
                decision.payload["voiceTranscript"] = voice_event.get("voiceTranscript", "")
                decision.payload["voiceMatchedPhrase"] = voice_event.get("voiceMatchedPhrase", "")
                decision.payload["voiceMatchKind"] = voice_event.get("voiceMatchKind", "")
                decision.payload["voiceSource"] = voice_event.get("voiceSource", "")
                decision.payload["voiceModelVersion"] = voice_event.get("voiceModelVersion", "")
                decision.payload["voiceEngine"] = voice_event.get("voiceEngine", "")
                decision.payload["voiceConfidenceRaw"] = round(
                    float(voice_event.get("confidence", voice_confidence)),
                    4,
                )
                if voice_event.get("voiceRecognitionConfidence") is not None:
                    decision.payload["voiceRecognitionConfidence"] = round(
                        float(voice_event.get("voiceRecognitionConfidence")),
                        4,
                    )

            # Send alert in background
            alert_dispatcher.dispatch_async(str(image_path), decision.payload)

        if decision.in_cooldown:
            sos_active = True
        elif not decision.should_trigger:
            sos_active = False

        processing_latency_ms = (time.perf_counter() - loop_started_at) * 1000.0
        frame_latency_samples.append(processing_latency_ms)

        if current_time - last_metrics_log_at >= 30 and frame_fps_samples and frame_latency_samples:
            avg_fps = sum(frame_fps_samples) / len(frame_fps_samples)
            avg_latency = sum(frame_latency_samples) / len(frame_latency_samples)
            print_startup(
                f"Loop metrics | avg_fps={avg_fps:.2f} | avg_latency_ms={avg_latency:.1f} | "
                f"gesture={active_gesture_engine} | voice={active_voice_engine} | gender={active_gender_engine}",
                "INFO",
            )
            last_metrics_log_at = current_time

        if current_time - last_retention_scan_at >= ALERT_RETENTION_SCAN_INTERVAL_SECONDS:
            retention_result = cleanup_alert_snapshots(
                Path(__file__).resolve().parent / "data" / "images",
                retention_days=ALERT_IMAGE_RETENTION_DAYS,
                protected_paths=alert_dispatcher.protected_image_paths(),
                logger=print_startup,
            )
            print_startup(
                f"Retention sweep | checked={retention_result['checked']} "
                f"deleted={retention_result['deleted']} protected={retention_result['protected']}",
                "INFO",
            )
            last_retention_scan_at = current_time

        # ---- Draw UI ----
        # Status text
        status_text = "🚨 SOS ACTIVE" if sos_active else "✓ Monitoring"
        status_color = (0, 0, 255) if sos_active else (0, 255, 0)
        
        cv2.putText(
            display_frame, status_text, (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, status_color, 2
        )
        
        # Gesture confidence indicator
        if gesture_confidence > 0:
            conf_text = f"Gesture: {gesture_label or 'SOS'} ({gesture_confidence:.1%})"
            cv2.putText(
                display_frame, conf_text, (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2
            )

        if gender_scene is not None and gender_scene.ready:
            scene_text = (
                f"Scene estimate: faces={gender_scene.face_count} | "
                f"M={gender_scene.male_count} F={gender_scene.female_count} U={gender_scene.unknown_gender_count}"
            )
            cv2.putText(
                display_frame,
                scene_text,
                (10, 125),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (255, 215, 0),
                2,
            )
            cv2.putText(
                display_frame,
                "Gender estimate is local and approximate",
                (10, 155),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (180, 180, 180),
                1,
            )
        elif GENDER_DETECTION_ENABLED and gender_runtime is not None:
            cv2.putText(
                display_frame,
                "Gender estimate unavailable",
                (10, 125),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 165, 255),
                2,
            )
        
        # FPS and frame counter
        fps_text = f"FPS: {fps:.1f} | Frame: {frame_count}"
        cv2.putText(
            display_frame, fps_text, (display_frame.shape[1] - 250, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1
        )
        
        if display_enabled:
            # Show frame
            try:
                cv2.imshow(window_name, display_frame)
            except Exception as e:
                print_startup(f"Display error: {e}", "ERROR")
                break

            # Check for quit key (wait 10ms for better responsiveness)
            key = cv2.waitKey(10) & 0xFF
            if key == ord('q'):
                print()
                print_startup("Quit key pressed")
                break

            # Check if window was closed
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                print()
                print_startup("Window closed by user")
                break
        else:
            # In headless mode, keep loop responsive and rely on Ctrl+C to exit.
            time.sleep(0.01)

except KeyboardInterrupt:
    print()
    print_startup("Interrupted by user (Ctrl+C)")

except Exception as e:
    print()
    print_startup(f"Unexpected error in main loop: {e}", "ERROR")
    import traceback
    traceback.print_exc()
    sys.stdout.flush()

finally:
    print()
    print_startup("Shutting down...")
    
    try:
        if cap is not None and cap.isOpened():
            cap.release()
            print_startup("✓ Camera released")
        else:
            print_startup("Camera was already closed", "WARN")
    except Exception as e:
        print_startup(f"Error releasing camera: {e}", "ERROR")

    try:
        if voice_sos is not None:
            voice_sos.stop_listening()
            print_startup("✓ Voice listener stopped")
    except Exception as e:
        print_startup(f"Error stopping voice listener: {e}", "WARN")

    try:
        if alert_dispatcher is not None:
            alert_dispatcher.stop()
            print_startup("✓ Alert retry worker stopped")
    except Exception as e:
        print_startup(f"Error stopping alert dispatcher: {e}", "WARN")

    if display_enabled:
        try:
            cv2.destroyAllWindows()
            print_startup("✓ Windows closed")
        except Exception as e:
            print_startup(f"Error closing windows: {e}", "ERROR")
    
    print()
    print("=" * 60)
    print_startup("System stopped", "SYSTEM")
    print_startup(f"Total frames processed: {frame_count}", "SYSTEM")
    print("=" * 60)
    sys.stdout.flush()



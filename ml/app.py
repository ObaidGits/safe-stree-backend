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
import platform
from datetime import datetime


def print_startup(message, prefix="INFO"):
    """Print startup message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{prefix}] {message}")
    sys.stdout.flush()


def env_enabled(var_name, default="1"):
    value = os.environ.get(var_name, default)
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def get_camera_backends():
    system_name = platform.system().lower()
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

    unique_candidates = []
    seen = set()
    for backend_name, backend_id in candidates:
        if backend_id in seen:
            continue
        seen.add(backend_id)
        unique_candidates.append((backend_name, backend_id))

    return unique_candidates


def open_camera(index, backend_id):
    if backend_id == cv2.CAP_ANY:
        return cv2.VideoCapture(index)
    return cv2.VideoCapture(index, backend_id)


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

VOICE_ENABLED = env_enabled("ENABLE_VOICE_SOS", "1")

try:
    from sos_gesture.gesture_detector import detect_sos_stable
    print_startup("✓ Gesture detection module loaded (OpenCV Only)")
except ImportError as e:
    print_startup(f"✗ Failed to load gesture module: {e}", "ERROR")
    sys.exit(1)

VoiceSOSTrigger = None
if VOICE_ENABLED:
    try:
        from sos_voice.voice import VoiceSOSTrigger
        print_startup("✓ Voice detection module loaded")
    except ImportError as e:
        print_startup(f"Voice module unavailable, continuing without voice: {e}", "WARN")
else:
    print_startup("Voice detection disabled via ENABLE_VOICE_SOS=0", "WARN")

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
        voice_sos = VoiceSOSTrigger()
        voice_sos.start_listening()
        print_startup("✓ Voice listener started")
    except Exception as e:
        print_startup(f"Voice listener error: {e}", "WARN")
else:
    print_startup("Voice listener disabled", "WARN")

print()

# ============================================================
# CAMERA SETUP
# ============================================================
print_startup("Initializing camera...")

def find_camera():
    """Find first working camera index and backend."""
    max_camera_index = max(1, int(os.environ.get("MAX_CAMERA_INDEX", "8")))
    forced_camera_index = os.environ.get("CAMERA_INDEX")

    if forced_camera_index is not None:
        try:
            camera_indices = [int(forced_camera_index)]
        except ValueError:
            print_startup(
                f"Invalid CAMERA_INDEX='{forced_camera_index}', falling back to 0..{max_camera_index - 1}",
                "WARN",
            )
            camera_indices = list(range(max_camera_index))
    else:
        camera_indices = list(range(max_camera_index))

    attempts = []
    for backend_name, backend_id in get_camera_backends():
        for index in camera_indices:
            attempts.append(f"{backend_name}:{index}")
            cap = None
            try:
                cap = open_camera(index, backend_id)
                if cap.isOpened():
                    success, frame = cap.read()
                    if success and frame is not None:
                        cap.release()
                        return index, backend_name, backend_id
            except Exception:
                pass
            finally:
                if cap is not None:
                    cap.release()

    if attempts:
        preview_attempts = ", ".join(attempts[:10])
        suffix = " ..." if len(attempts) > 10 else ""
        print_startup(f"Camera probe attempts: {preview_attempts}{suffix}", "WARN")

    return -1, None, None


camera_index, camera_backend_name, camera_backend = find_camera()

if camera_index == -1:
    print_startup("No camera detected", "ERROR")
    print_startup("Set CAMERA_INDEX or increase MAX_CAMERA_INDEX if your camera index is higher", "ERROR")
    sys.exit(1)

print_startup(f"Camera found at index {camera_index} using {camera_backend_name}")

# Open camera
cap = open_camera(camera_index, camera_backend)

if not cap.isOpened():
    print_startup("Failed to open camera", "ERROR")
    sys.exit(1)

# Configure camera
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

display_enabled = env_enabled("ENABLE_DISPLAY", "1")
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

print_startup("✓ Camera initialized")
print()


# ============================================================
# MAIN MONITORING LOOP
# ============================================================
print("=" * 60)
print_startup("SYSTEM ACTIVE - Monitoring Started", "SYSTEM")
print("=" * 60)
print_startup("Press 'q' to quit")
print()

# SOS state tracking
sos_active = False
cooldown_end_time = 0
COOLDOWN_SECONDS = 6


def send_sos_alert(image_path):
    """Send SOS alert to backend in background thread"""
    try:
        print_startup("Sending SOS alert to backend...", "ALERT")
        success = send_sos_to_cctv_route(image_path=image_path)
        if success:
            print_startup("✓ SOS alert sent successfully", "ALERT")
        else:
            print_startup("Failed to send SOS alert to backend", "ERROR")
    except Exception as e:
        print_startup(f"Failed to send SOS: {e}", "ERROR")


try:
    frame_count = 0
    last_frame_time = time.time()
    gesture_initialized = False
    
    print_startup("Entering main monitoring loop...")
    
    while True:
        # Check if camera is still open
        if not cap.isOpened():
            print_startup("Camera connection lost - attempting to reconnect...", "WARN")
            time.sleep(1)
            cap = open_camera(camera_index, camera_backend)
            if not cap.isOpened():
                print_startup("Failed to reconnect to camera", "ERROR")
                break
            print_startup("Camera reconnected successfully", "INFO")
        
        # Read frame
        success, frame = cap.read()
        if not success:
            print_startup("Failed to read frame - retrying...", "WARN")
            time.sleep(0.1)
            continue
        
        # Flip frame horizontally for mirror effect
        frame = cv2.flip(frame, 1)
        display_frame = copy.deepcopy(frame)
        
        current_time = time.time()
        frame_count += 1
        
        # Track FPS
        fps = 1.0 / (current_time - last_frame_time) if (current_time - last_frame_time) > 0 else 0
        last_frame_time = current_time
        
        # ---- Detect SOS Gestures ----
        gesture_detected = False
        gesture_confidence = 0.0
        
        try:
            gesture_detected, gesture_confidence = detect_sos_stable(frame, fps=fps)
            if not gesture_initialized:
                gesture_initialized = True
                print_startup("✓ Gesture detection initialized", "INFO")
        except Exception as e:
            print_startup(f"Gesture detection error: {e}", "ERROR")
            # Continue monitoring even if gesture detection fails
        
        # ---- Check Voice SOS ----
        voice_detected = False
        try:
            voice_detected = voice_sos.check_triggered() if voice_sos else False
        except Exception as e:
            print_startup(f"Voice detection error: {e}", "ERROR")
        
        # ---- Determine if SOS should trigger ----
        should_trigger_sos = False
        trigger_reason = ""
        
        if current_time > cooldown_end_time:  # Not in cooldown
            if gesture_detected:
                should_trigger_sos = True
                trigger_reason = f"Gesture (conf: {gesture_confidence:.2f})"
            elif voice_detected:
                should_trigger_sos = True
                trigger_reason = "Voice Command"
        
        # ---- Trigger SOS Alert ----
        if should_trigger_sos and not sos_active:
            sos_active = True
            cooldown_end_time = current_time + COOLDOWN_SECONDS
            
            # Save alert image to organized directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = f"data/images/sos_alert_{timestamp}.jpg"
            image_saved = cv2.imwrite(image_path, frame)

            if not image_saved:
                print_startup("Failed to save SOS image. Alert not dispatched.", "ERROR")
                sos_active = False
                cooldown_end_time = 0
                continue
            
            print()
            print_startup(f"🚨 SOS TRIGGERED: {trigger_reason}", "ALERT")
            print_startup(f"Image saved: {image_path}", "ALERT")
            print()
            
            # Send alert in background
            threading.Thread(target=send_sos_alert, args=(image_path,), daemon=True).start()
        
        # ---- Reset SOS state after cooldown ----
        if current_time > cooldown_end_time:
            sos_active = False
        
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
            conf_text = f"Gesture: {gesture_confidence:.1%}"
            cv2.putText(
                display_frame, conf_text, (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2
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



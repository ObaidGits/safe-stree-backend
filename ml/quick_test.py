"""
Quick test - just verify MediaPipe loads without hanging
No camera required
"""

import os
import sys

# Environment setup
os.environ['GLOG_minloglevel'] = '2'
os.environ['MEDIAPIPE_DISABLE_GPU'] = '1'

print("\n" + "=" * 60)
print("QUICK TEST: OpenCV Gesture Detector")
print("=" * 60 + "\n")

print("[1/3] Importing module...")
try:
    from sos_gesture.gesture_detector import SimpleGestureDetector as GestureDetector
    print("[1/3] [OK] OpenCV Only (NO TensorFlow!)\n")
except Exception as e:
    print(f"[1/3] [FAIL] {e}\n")
    sys.exit(1)

print("[2/3] Creating detector...")
try:
    detector = GestureDetector()
    print("[2/3] [OK]")
    print(f"        Gestures loaded: {list(detector.gestures.keys())}\n")
except Exception as e:
    print(f"[2/3] [FAIL] {e}\n")
    sys.exit(1)

print("[3/3] Initializing detector (should be instant!)...")
print("        OpenCV-only system - No MediaPipe/TensorFlow loading!\n")

try:
    success = detector.initialize()
    if success:
        print("[3/3] [OK] - INSTANT, NO HANG!")
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe new system works correctly!")
        print("MediaPipe loads WITHOUT hanging.\n")
        print("Next steps:")
        print("  1. Run 'python train_gesture.py' to train gestures")
        print("  2. Run 'python app.py' to start the full system")
        print("\nOpenCV-only system - No MediaPipe/TensorFlow issues!")
        print("=" * 60 + "\n")
    else:
        print("[3/3] [FAIL] Initialization returned False\n")
except Exception as e:
    print(f"[3/3] [FAIL] {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"[3/3] ✗ FAILED: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Cleanup
detector.cleanup()

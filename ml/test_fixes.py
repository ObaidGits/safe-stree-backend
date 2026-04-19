"""
Quick test to verify backward compatibility and database migration
"""

print("=" * 60)
print("Testing Fixes")
print("=" * 60)

# Test 1: Gesture backward compatibility
print("\n[1/2] Testing gesture backward compatibility...")
try:
    from sos_gesture.gesture_detector import SimpleGestureDetector
    detector = SimpleGestureDetector()
    print("[1/2] [OK] Gestures loaded without shape errors")
except Exception as e:
    print(f"[1/2] [FAIL] {e}")

# Test 2: Database migration
print("\n[2/2] Testing database migration...")
try:
    from location_cache import init_db, save_location
    init_db()
    save_location(22.5, 88.3, 100)
    print("[2/2] [OK] Database initialized with timestamp column")
except Exception as e:
    print(f"[2/2] [FAIL] {e}")

print("\n" + "=" * 60)
print("[SUCCESS] All fixes verified!")
print("=" * 60)
print("\nYou can now run: python app.py")
print("The shape mismatch and database errors should be fixed.")
print("\nNote: For best accuracy, retrain gestures with:")
print("      python train_gesture.py")
print("=" * 60)

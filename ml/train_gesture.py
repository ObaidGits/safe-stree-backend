"""
Gesture Training Interface - OpenCV Only
NO MediaPipe/TensorFlow - uses pure OpenCV for reliability
"""

import cv2
import numpy as np
import os
import sys
import platform
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sos_gesture.gesture_detector import SimpleGestureDetector


class SimpleGestureTrainer:
    """Enhanced training interface with quality feedback"""
    
    def __init__(self):
        self.detector = SimpleGestureDetector()
        self.cap = None
        self.recording = False
        self.current_gesture = None
        self.samples_collected = 0
        self.target_samples = 20  # Increased for better accuracy
        self.sample_quality_threshold = 0.75  # Minimum quality for samples
        self.required_gestures = ["SOS", "HELP", "OK", "_NEGATIVE"]
        self.min_samples_per_gesture = 20

    @staticmethod
    def get_display_name(gesture_name):
        return "NEGATIVE (non-SOS)" if gesture_name == "_NEGATIVE" else gesture_name

    def print_dataset_balance(self):
        print("\n[Training] Dataset coverage:")
        for gesture_name in self.required_gestures:
            count = len(self.detector.gestures.get(gesture_name, []))
            shortfall = max(0, self.min_samples_per_gesture - count)
            status = "ready" if shortfall == 0 else f"need {shortfall} more"
            print(f"  - {self.get_display_name(gesture_name)}: {count} samples ({status})")

        sos_count = len(self.detector.gestures.get("SOS", []))
        for gesture_name in ["HELP", "OK", "_NEGATIVE"]:
            class_count = len(self.detector.gestures.get(gesture_name, []))
            if sos_count >= self.min_samples_per_gesture and class_count < max(10, sos_count // 2):
                print(
                    f"[Training] Warning: {self.get_display_name(gesture_name)} is underrepresented vs SOS."
                )
    
    def print_instructions(self):
        """Print training instructions"""
        print("\n" + "=" * 70)
        print("GESTURE TRAINING SYSTEM (OpenCV Only - NO TensorFlow!)")
        print("=" * 70)
        print("\nInstructions:")
        print("  1. Position your hand clearly in front of camera")
        print("  2. Ensure good lighting and plain background")
        print("  3. Press key to start recording:")
        print("     [S] - Record SOS gesture")
        print("     [H] - Record HELP gesture") 
        print("     [O] - Record OK gesture")
        print("     [N] - Record NEGATIVE (non-SOS) hand poses")
        print("     [C] - Record CUSTOM gesture")
        print("  4. Press SPACE to capture each sample")
        print("  5. Press [Q] to quit")
        print("\nTips:")
        print("  - Keep hand in center of camera view")
        print("  - Use plain background (wall, desk)")
        print("  - Ensure your skin is clearly visible")
        print("  - Record with different hand angles")
        print("  - 20 samples per gesture recommended")
        print("  - Watch quality indicator for good samples")
        print("=" * 70 + "\n")
    
    def start_camera(self):
        """Initialize camera"""
        print("[Camera] Searching for camera...")

        max_camera_index = max(1, int(os.environ.get("MAX_CAMERA_INDEX", "8")))
        forced_camera_index = os.environ.get("CAMERA_INDEX")

        if forced_camera_index is not None:
            try:
                camera_indices = [int(forced_camera_index)]
            except ValueError:
                print(
                    f"[Camera] Invalid CAMERA_INDEX='{forced_camera_index}', falling back to 0..{max_camera_index - 1}"
                )
                camera_indices = list(range(max_camera_index))
        else:
            camera_indices = list(range(max_camera_index))

        system_name = platform.system().lower()
        if system_name == "windows":
            backend_candidates = [
                ("CAP_DSHOW", cv2.CAP_DSHOW),
                ("CAP_MSMF", getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)),
                ("CAP_ANY", cv2.CAP_ANY),
            ]
        elif system_name == "linux":
            backend_candidates = [
                ("CAP_V4L2", getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)),
                ("CAP_GSTREAMER", getattr(cv2, "CAP_GSTREAMER", cv2.CAP_ANY)),
                ("CAP_ANY", cv2.CAP_ANY),
            ]
        elif system_name == "darwin":
            backend_candidates = [
                ("CAP_AVFOUNDATION", getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY)),
                ("CAP_ANY", cv2.CAP_ANY),
            ]
        else:
            backend_candidates = [("CAP_ANY", cv2.CAP_ANY)]

        unique_backends = []
        seen = set()
        for backend_name, backend_id in backend_candidates:
            if backend_id in seen:
                continue
            seen.add(backend_id)
            unique_backends.append((backend_name, backend_id))

        for backend_name, backend_id in unique_backends:
            for i in camera_indices:
                if backend_id == cv2.CAP_ANY:
                    cap = cv2.VideoCapture(i)
                else:
                    cap = cv2.VideoCapture(i, backend_id)

                if not cap.isOpened():
                    cap.release()
                    continue

                success, frame = cap.read()
                if not success or frame is None:
                    cap.release()
                    continue

                self.cap = cap
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                print(f"[Camera] ✓ Camera found at index {i} using {backend_name}")
                return True
        
        print("[Camera] ✗ No camera found")
        return False
    
    def record_gesture(self, gesture_name):
        """Record samples for a gesture"""
        display_name = self.get_display_name(gesture_name)
        print(f"\n[Training] Recording: {display_name}")
        print(f"[Training] Target: {self.target_samples} samples")
        print("[Training] Press SPACE to capture, ESC to stop\n")
        
        self.current_gesture = gesture_name
        self.samples_collected = 0
        self.recording = True
        
        while self.recording and self.samples_collected < self.target_samples:
            success, frame = self.cap.read()
            if not success:
                continue
            
            frame = cv2.flip(frame, 1)
            display_frame = frame.copy()
            
            # Detect hand
            contour, mask = self.detector.detect_hand_contour(frame)
            
            # Calculate sample quality if hand detected
            quality_score = 0.0
            quality_color = (0, 0, 255)  # Red = poor
            quality_text = "Poor"
            
            if contour is not None:
                area = cv2.contourArea(contour)
                perimeter = cv2.arcLength(contour, True)
                
                # Quality factors
                size_ok = 10000 < area < 150000
                shape_ok = perimeter > 300
                circularity = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
                shape_quality = circularity > 0.1  # Not too circular (should have fingers)
                
                # Calculate quality score
                quality_score = 0.0
                if size_ok:
                    quality_score += 0.4
                if shape_ok:
                    quality_score += 0.3
                if shape_quality:
                    quality_score += 0.3
                
                # Set quality indicator
                if quality_score >= 0.8:
                    quality_color = (0, 255, 0)  # Green = excellent
                    quality_text = "Excellent"
                elif quality_score >= 0.6:
                    quality_color = (0, 255, 255)  # Yellow = good
                    quality_text = "Good"
                elif quality_score >= 0.4:
                    quality_color = (0, 165, 255)  # Orange = fair
                    quality_text = "Fair"
                
                # Draw contour with color based on quality
                cv2.drawContours(display_frame, [contour], -1, quality_color, 2)
                
                # Draw bounding box
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
            
            # Display status
            status_text = f"Gesture: {display_name} | Samples: {self.samples_collected}/{self.target_samples}"
            cv2.putText(display_frame, status_text, (10, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            instruction_text = "SPACE = Capture | ESC = Stop"
            cv2.putText(display_frame, instruction_text, (10, 80),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            # Hand detection and quality status
            if contour is not None:
                status = f"Hand Detected | Quality: {quality_text} ({quality_score:.1%})"
                cv2.putText(display_frame, status, (10, 120),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, quality_color, 2)
            else:
                cv2.putText(display_frame, "No Hand - Adjust position/lighting", (10, 120),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Show mask in corner
            mask_small = cv2.resize(mask, (320, 180))
            mask_bgr = cv2.cvtColor(mask_small, cv2.COLOR_GRAY2BGR)
            display_frame[10:190, display_frame.shape[1]-330:display_frame.shape[1]-10] = mask_bgr
            cv2.putText(display_frame, "Hand Mask", 
                       (display_frame.shape[1]-320, 205),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            cv2.imshow("Gesture Training", display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == 27:  # ESC
                print(f"[Training] Stopped recording {display_name}")
                self.recording = False
                break
            
            elif key == 32:  # SPACE
                if contour is not None:
                    # Check quality before saving
                    if quality_score < self.sample_quality_threshold:
                        print(f"[Training] ✗ Sample quality too low ({quality_score:.1%})")
                        print(f"[Training]    Try: Better lighting, plain background, full hand visible")
                        continue
                    
                    # Extract and save features
                    features = self.detector.extract_features(contour, frame.shape)
                    
                    if features:
                        self.detector.save_gesture(gesture_name, features)
                        self.samples_collected += 1
                        print(f"[Training] ✓ Sample {self.samples_collected}/{self.target_samples} - Quality: {quality_text}")
                        cv2.waitKey(300)  # Brief pause
                    else:
                        print("[Training] ✗ Failed to extract features")
                else:
                    print("[Training] ✗ No hand detected")
        
        if self.samples_collected >= self.target_samples:
            print(f"\n[Training] ✓ Completed training for {display_name}!")

        self.print_dataset_balance()
        
        return True
    
    def run(self):
        """Main training loop"""
        self.print_instructions()
        
        if not self.start_camera():
            return
        
        cv2.namedWindow("Gesture Training", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Gesture Training", 1280, 720)
        
        print("[Training] Camera ready!")
        print("[Training] Press S/H/O/N/C to train, Q to quit\n")
        
        while True:
            success, frame = self.cap.read()
            if not success:
                continue
            
            frame = cv2.flip(frame, 1)
            display_frame = frame.copy()
            
            # Detect hand for preview
            contour, mask = self.detector.detect_hand_contour(frame)
            
            if contour is not None:
                cv2.drawContours(display_frame, [contour], -1, (0, 255, 0), 2)
            
            # Display menu
            y_pos = 50
            menu_items = [
                "TRAINING MENU:",
                "[S] - Train SOS",
                "[H] - Train HELP",
                "[O] - Train OK",
                "[N] - Train NEGATIVE",
                "[C] - Train CUSTOM",
                "[Q] - Quit"
            ]
            
            for i, item in enumerate(menu_items):
                color = (255, 255, 255) if i == 0 else (0, 255, 255)
                cv2.putText(display_frame, item, (10, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                y_pos += 40
            
            # Show trained gestures
            if self.detector.gestures:
                y_pos += 20
                cv2.putText(display_frame, "Trained Gestures:", (10, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                y_pos += 35
                
                for gesture_name, samples in self.detector.gestures.items():
                    text = f" {self.get_display_name(gesture_name)}: {len(samples)} samples"
                    cv2.putText(display_frame, text, (10, y_pos),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    y_pos += 30
            
            # Show mask preview
            mask_small = cv2.resize(mask, (320, 180))
            mask_bgr = cv2.cvtColor(mask_small, cv2.COLOR_GRAY2BGR)
            display_frame[10:190, display_frame.shape[1]-330:display_frame.shape[1]-10] = mask_bgr
            
            cv2.imshow("Gesture Training", display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\n[Training] Exiting...")
                break
            elif key == ord('s'):
                self.record_gesture("SOS")
            elif key == ord('h'):
                self.record_gesture("HELP")
            elif key == ord('o'):
                self.record_gesture("OK")
            elif key == ord('n'):
                self.record_gesture("_NEGATIVE")
            elif key == ord('c'):
                print("\n[Training] Enter gesture name: ", end='')
                gesture_name = input().strip()
                if gesture_name:
                    self.record_gesture(gesture_name)
        
        # Cleanup
        self.cap.release()
        cv2.destroyAllWindows()
        
        print("\n[Training] Session complete!")
        print(f"[Training] Gestures saved to: {self.detector.model_file}")
        print("\n[Training] Run app.py to use trained gestures!\n")


if __name__ == "__main__":
    trainer = SimpleGestureTrainer()
    trainer.run()

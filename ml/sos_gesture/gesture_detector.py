"""
Simple Hand Gesture Recognition - OpenCV Only (No MediaPipe/TensorFlow)
Uses color-based hand detection and geometric analysis
GUARANTEED to work without hanging - no TensorFlow dependencies!
"""

import cv2
import numpy as np
import json
from pathlib import Path
from collections import deque
from datetime import datetime


class SimpleGestureDetector:
    """
    Hand gesture detector using pure OpenCV
    No MediaPipe, no TensorFlow - completely reliable!
    """
    
    def __init__(self, model_file="data/gestures/gestures.json"):
        self.model_file = Path(model_file)
        self.gestures = {}
        self.base_history_size = 20
        self.min_history_size = 12
        self.max_history_size = 30
        self.target_fps = 30.0
        self.runtime_fps = self.target_fps
        self.history = deque(maxlen=self.base_history_size)
        self.confidence_history = deque(maxlen=self.base_history_size)
        self.initialized = True
        
        # Adaptive HSV profiles for better skin detection in mixed lighting.
        self.skin_profiles = [
            ("default", np.array([0, 20, 70], dtype=np.uint8), np.array([20, 255, 255], dtype=np.uint8)),
            ("low_light", np.array([0, 15, 45], dtype=np.uint8), np.array([25, 255, 255], dtype=np.uint8)),
            ("bright", np.array([0, 30, 85], dtype=np.uint8), np.array([18, 220, 255], dtype=np.uint8)),
        ]
        self.active_skin_profile = self.skin_profiles[0][0]
        self.min_mask_coverage = 0.01
        self.max_mask_coverage = 0.45
        
        # Enhanced detection parameters
        self.min_contour_area = 8000  # Minimum hand size
        self.max_contour_area = 200000  # Maximum hand size
        self.gesture_confidence_threshold = 0.70  # Higher threshold for accuracy
        self.temporal_threshold = 0.65  # 65% of frames must match
        self.score_separation_threshold = 0.15
        self.temporal_decay = 0.6
        self.last_scores = {}

        # Reuse morphological kernels to avoid per-frame recreation.
        self.kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        
        print("[Gesture] Enhanced OpenCV detector initialized")
        self.load_gestures()

    def _resize_history_buffers(self, history_size):
        history_size = max(self.min_history_size, min(self.max_history_size, int(history_size)))
        if history_size == self.history.maxlen:
            return

        self.history = deque(self.history, maxlen=history_size)
        self.confidence_history = deque(self.confidence_history, maxlen=history_size)

    def update_runtime_fps(self, fps):
        """Adapt temporal window to observed FPS for consistent trigger behavior."""
        if fps is None or fps <= 0:
            return

        self.runtime_fps = (self.runtime_fps * 0.85) + (float(fps) * 0.15)
        fps_scale = min(1.4, max(0.7, self.runtime_fps / self.target_fps))
        target_window = round(self.base_history_size * fps_scale)
        self._resize_history_buffers(target_window)

    def _build_skin_mask(self, hsv_frame, lower_skin, upper_skin):
        mask = cv2.inRange(hsv_frame, lower_skin, upper_skin)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel_small, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel_large, iterations=2)
        mask = cv2.GaussianBlur(mask, (7, 7), 0)
        return cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)[1]
    
    def initialize(self):
        """Already initialized - no loading needed!"""
        return True
    
    def detect_hand_contour(self, frame):
        """
        Enhanced hand detection with adaptive preprocessing
        Returns largest valid hand contour or None
        """
        # Convert to HSV and normalize illumination on V channel.
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h_channel, s_channel, v_channel = cv2.split(hsv)
        v_channel = self.clahe.apply(v_channel)
        hsv = cv2.merge((h_channel, s_channel, v_channel))
        hsv = cv2.bilateralFilter(hsv, 9, 75, 75)

        best_contour = None
        best_mask = None
        best_score = -1.0

        for profile_name, lower_skin, upper_skin in self.skin_profiles:
            mask = self._build_skin_mask(hsv, lower_skin, upper_skin)
            coverage = cv2.countNonZero(mask) / float(mask.shape[0] * mask.shape[1])

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid_contours = [
                c for c in contours
                if self.min_contour_area < cv2.contourArea(c) < self.max_contour_area
            ]

            if not valid_contours:
                if best_mask is None:
                    best_mask = mask
                continue

            contour = max(valid_contours, key=cv2.contourArea)
            contour_area = cv2.contourArea(contour)

            penalty = 0.0
            if coverage < self.min_mask_coverage:
                penalty += (self.min_mask_coverage - coverage) * self.max_contour_area
            elif coverage > self.max_mask_coverage:
                penalty += (coverage - self.max_mask_coverage) * self.max_contour_area

            score = contour_area - penalty
            if score > best_score:
                best_score = score
                best_contour = contour
                best_mask = mask
                self.active_skin_profile = profile_name

        if best_contour is None:
            if best_mask is None:
                best_mask = np.zeros((frame.shape[0], frame.shape[1]), dtype=np.uint8)
            return None, best_mask

        return best_contour, best_mask
    
    def extract_features(self, contour, frame_shape):
        """
        Enhanced feature extraction with more discriminative features
        Returns comprehensive feature vector
        """
        if contour is None:
            return None
        
        try:
            # Calculate convex hull
            hull = cv2.convexHull(contour, returnPoints=False)
            hull_points = cv2.convexHull(contour)
            
            # Find convexity defects (spaces between fingers)
            defects = cv2.convexityDefects(contour, hull) if len(contour) > 3 else None
            
            # Calculate moments
            moments = cv2.moments(contour)
            
            # Basic geometric features
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            hull_area = cv2.contourArea(hull_points)
            
            # Circularity (4*pi*area / perimeter^2)
            circularity = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
            
            # Aspect ratio and orientation
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = float(w) / h if h > 0 else 0
            
            # Extent (contour area / bounding box area)
            rect_area = w * h
            extent = float(area) / rect_area if rect_area > 0 else 0
            
            # Solidity (contour area / convex hull area)
            solidity = float(area) / hull_area if hull_area > 0 else 0
            
            # Convexity (perimeter of convex hull / perimeter of contour)
            hull_perimeter = cv2.arcLength(hull_points, True)
            convexity = hull_perimeter / perimeter if perimeter > 0 else 0
            
            # Compactness
            compactness = (perimeter ** 2) / area if area > 0 else 0
            
            # Count fingers (enhanced algorithm)
            finger_count = 0
            defect_distances = []
            defect_depth_threshold = max(6000.0, (np.sqrt(max(area, 1.0)) * 256.0 * 0.18))
            
            if defects is not None:
                for i in range(defects.shape[0]):
                    s, e, f, d = defects[i, 0]
                    start = tuple(contour[s][0])
                    end = tuple(contour[e][0])
                    far = tuple(contour[f][0])
                    
                    # Calculate angle at defect point
                    a = np.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)
                    b = np.sqrt((far[0] - start[0]) ** 2 + (far[1] - start[1]) ** 2)
                    c = np.sqrt((end[0] - far[0]) ** 2 + (end[1] - far[1]) ** 2)
                    
                    if b * c > 0:
                        cosine = (b ** 2 + c ** 2 - a ** 2) / (2 * b * c)
                        cosine = np.clip(cosine, -1.0, 1.0)
                        angle = np.arccos(cosine)
                    else:
                        angle = 0
                    
                    # Enhanced finger detection
                    if angle <= np.pi / 2 and d > defect_depth_threshold:
                        finger_count += 1
                        defect_distances.append(d)
            
            # Finger count (capped at 5)
            finger_count = min(finger_count + 1, 5)
            
            # Average defect depth (indicator of finger spread)
            avg_defect_depth = np.mean(defect_distances) if defect_distances else 0
            
            # Hu Moments (7 rotation-invariant shape descriptors)
            hu_moments = cv2.HuMoments(moments).flatten()
            # Apply log transform to reduce scale variation
            hu_moments = -np.sign(hu_moments) * np.log10(np.abs(hu_moments) + 1e-10)
            
            # Additional shape descriptors
            # Eccentricity using fitted ellipse
            if len(contour) >= 5:
                ellipse = cv2.fitEllipse(contour)
                major_axis = max(ellipse[1])
                minor_axis = min(ellipse[1])
                eccentricity = np.sqrt(1 - (minor_axis / major_axis) ** 2) if major_axis > 0 else 0
            else:
                eccentricity = 0
            
            # Create comprehensive feature vector
            features = [
                circularity,
                aspect_ratio,
                extent,
                solidity,
                convexity,
                compactness,
                float(finger_count) / 5.0,  # Normalized
                area / (frame_shape[0] * frame_shape[1]),  # Normalized area
                avg_defect_depth / 100000,  # Normalized
                eccentricity,
            ] + hu_moments.tolist()
            
            return features
            
        except Exception as e:
            print(f"[Gesture] Feature extraction error: {e}")
            return None
    
    def compare_features(self, features1, features2):
        """
        Enhanced feature comparison using weighted distance
        Returns similarity score (0-1)
        """
        if features1 is None or features2 is None:
            return 0.0
        
        f1 = np.array(features1, dtype=np.float32)
        f2 = np.array(features2, dtype=np.float32)

        target_len = max(len(f1), len(f2))
        if len(f1) < target_len:
            f1 = np.pad(f1, (0, target_len - len(f1)), constant_values=0.0)
        if len(f2) < target_len:
            f2 = np.pad(f2, (0, target_len - len(f2)), constant_values=0.0)

        # Weighted Euclidean distance (give more weight to shape descriptors)
        weights = np.array([1.5, 1.5, 1.2, 1.2, 1.2, 1.0, 2.0, 1.0, 1.5, 1.3] + [0.8] * 7, dtype=np.float32)
        if len(weights) < target_len:
            weights = np.pad(weights, (0, target_len - len(weights)), constant_values=0.8)
        else:
            weights = weights[:target_len]
        
        # Calculate weighted distance
        distance = np.sqrt(np.sum(weights * (f1 - f2) ** 2))
        
        # Convert to similarity using exponential decay
        similarity = np.exp(-distance / 5.0)
        
        return similarity
    
    def detect_gesture(self, frame):
        """
        Enhanced gesture detection with confidence scoring
        Returns: (gesture_name, confidence)
        """
        # Detect hand
        contour, mask = self.detect_hand_contour(frame)
        
        if contour is None:
            self.history.append(None)
            self.confidence_history.append(0.0)
            return None, 0.0
        
        # Extract features
        features = self.extract_features(contour, frame.shape)
        
        if features is None:
            self.history.append(None)
            self.confidence_history.append(0.0)
            return None, 0.0
        
        # Compare with trained gestures using enhanced scoring
        best_match = None
        best_score = 0.0
        all_scores = {}
        
        for gesture_name, trained_features_list in self.gestures.items():
            scores = []
            for trained_features in trained_features_list:
                score = self.compare_features(features, trained_features)
                scores.append(score)
            
            # Use weighted average (recent samples more important)
            if scores:
                weights = np.linspace(0.8, 1.2, len(scores))
                avg_score = np.average(scores, weights=weights)
            else:
                avg_score = 0.0
            
            all_scores[gesture_name] = avg_score
            
            if avg_score > best_score:
                best_score = avg_score
                best_match = gesture_name

        self.last_scores = all_scores
        
        # Dynamic threshold based on score separation
        if best_match and len(all_scores) > 1:
            sorted_scores = sorted(all_scores.values(), reverse=True)
            score_separation = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 1.0
            # Require good separation between top matches
            if score_separation < self.score_separation_threshold:
                best_score *= 0.55  # Penalize ambiguous detections

        negative_score = all_scores.get("_NEGATIVE", 0.0)
        if best_match == "SOS" and negative_score >= max(0.62, best_score - 0.05):
            best_match = None
            best_score *= 0.5

        if best_match == "_NEGATIVE":
            self.history.append(None)
            self.confidence_history.append(best_score * 0.5)
            return None, best_score * 0.5
        
        # Apply threshold
        if best_score >= self.gesture_confidence_threshold:
            self.history.append(best_match)
            self.confidence_history.append(best_score)
            return best_match, best_score
        else:
            self.history.append(None)
            self.confidence_history.append(best_score)
            return None, best_score
    
    def detect_sos_stable(self, frame, fps=None):
        """
        Enhanced SOS detection with temporal smoothing and confidence weighting
        Returns: (is_sos: bool, confidence: float)
        """
        self.update_runtime_fps(fps)
        self.detect_gesture(frame)

        if not self.history:
            return False, 0.0

        history_items = list(self.history)
        confidence_items = list(self.confidence_history)

        weights = np.linspace(self.temporal_decay, 1.0, len(history_items), dtype=np.float32)
        weights = weights / np.sum(weights)
        
        # Calculate weighted temporal confidence
        sos_flags = np.array([1.0 if g == "SOS" else 0.0 for g in history_items], dtype=np.float32)
        temporal_confidence = float(np.dot(sos_flags, weights))
        
        # Weighted average confidence of SOS detections
        sos_indices = [i for i, g in enumerate(history_items) if g == "SOS"]
        if sos_indices:
            sos_weights = np.array([weights[i] for i in sos_indices], dtype=np.float32)
            sos_weights = sos_weights / np.sum(sos_weights)
            sos_confidences = np.array([confidence_items[i] for i in sos_indices], dtype=np.float32)
            avg_sos_confidence = float(np.dot(sos_confidences, sos_weights))
        else:
            avg_sos_confidence = 0.0
        
        # Combined confidence (temporal + average quality)
        combined_confidence = (temporal_confidence * 0.7) + (avg_sos_confidence * 0.3)
        
        # SOS detected if temporal threshold met AND good average confidence
        is_sos = (temporal_confidence >= self.temporal_threshold and 
                  avg_sos_confidence >= (self.gesture_confidence_threshold - 0.05))
        
        return is_sos, combined_confidence
    
    def draw_detection(self, frame, contour, gesture_name, confidence):
        """
        Draw detection visualization on frame
        """
        if contour is None:
            return frame
        
        # Draw contour
        cv2.drawContours(frame, [contour], -1, (0, 255, 0), 2)
        
        # Draw bounding box
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        
        # Draw gesture label
        if gesture_name:
            label = f"{gesture_name}: {confidence:.2f}"
            cv2.putText(frame, label, (x, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        return frame
    
    def load_gestures(self):
        """Load trained gestures from JSON"""
        if not self.model_file.exists():
            print(f"[Gesture] No trained gestures at {self.model_file}")
            print("[Gesture] Run train_gesture.py to train gestures")
            self.gestures = {}
            return
        
        try:
            with open(self.model_file, 'r') as f:
                data = json.load(f)
                loaded_gestures = data.get('gestures', {})
            
            # Backward compatibility: pad old 13-feature samples to 17 features
            self.gestures = {}
            for gesture_name, samples in loaded_gestures.items():
                padded_samples = []
                for sample in samples:
                    if len(sample) == 13:
                        # Pad with default values for the 4 new features
                        # New features: convexity, compactness, eccentricity, + 1 Hu moment
                        padded = sample + [0.0, 0.0, 0.0, 0.0]
                        padded_samples.append(padded)
                        print(f"[Gesture] Upgraded {gesture_name} sample: 13 → 17 features")
                    elif len(sample) == 17:
                        padded_samples.append(sample)
                    else:
                        print(f"[Gesture] Warning: Unexpected feature count {len(sample)} for {gesture_name}")
                        padded_samples.append(sample)
                
                self.gestures[gesture_name] = padded_samples
            
            gesture_count = len(self.gestures)
            sample_count = sum(len(samples) for samples in self.gestures.values())
            
            print(f"[Gesture] Loaded {gesture_count} gestures ({sample_count} samples)")
            print(f"[Gesture] Available: {list(self.gestures.keys())}")
        except Exception as e:
            print(f"[Gesture] Error loading gestures: {e}")
            self.gestures = {}
    
    def save_gesture(self, gesture_name, features):
        """Save gesture sample"""
        if gesture_name not in self.gestures:
            self.gestures[gesture_name] = []
        
        self.gestures[gesture_name].append(features)
        
        data = {
            'gestures': self.gestures,
            'updated': datetime.now().isoformat()
        }
        
        self.model_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.model_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"[Gesture] Saved '{gesture_name}' (total: {len(self.gestures[gesture_name])})")
    
    def cleanup(self):
        """No resources to release - pure OpenCV!"""
        pass


# Global detector instance
_detector = None


def detect_sos_stable(frame, fps=None):
    """
    Simple wrapper for backward compatibility
    """
    global _detector
    if _detector is None:
        _detector = SimpleGestureDetector()
    
    return _detector.detect_sos_stable(frame, fps=fps)

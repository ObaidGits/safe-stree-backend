"""Aggregate hand and voice detections into a single alert decision."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class AlertDecision:
    should_trigger: bool
    in_cooldown: bool
    trigger_type: str = ""
    trigger_label: str = ""
    trigger_reason: str = ""
    confidence: float = 0.0
    event_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    cooldown_until: float = 0.0


class SOSEventAggregator:
    """Keep trigger state, apply cooldown, and build alert payloads."""

    def __init__(
        self,
        *,
        camera_id: str,
        camera_name: str = "",
        camera_location_label: str = "",
        cooldown_seconds: int = 6,
        enable_combined_trigger: bool = False,
        combined_window_seconds: int = 5,
        model_versions: dict[str, str] | None = None,
    ) -> None:
        self.camera_id = camera_id or "cam-main-gate-01"
        self.camera_name = camera_name.strip()
        self.camera_location_label = camera_location_label.strip()
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self.enable_combined_trigger = bool(enable_combined_trigger)
        self.combined_window_seconds = max(0, int(combined_window_seconds))
        self.model_versions = model_versions or {
            "gesture": "legacy_opencv",
            "voice": "vosk",
            "gender": "disabled",
        }

        self.cooldown_until = 0.0
        self.last_hand_detection_at: float | None = None
        self.last_voice_detection_at: float | None = None

    @staticmethod
    def _normalize_confidence(value: float | int | None) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, confidence))

    def is_in_cooldown(self, current_time: float) -> bool:
        return current_time < self.cooldown_until

    def reset_cooldown(self) -> None:
        self.cooldown_until = 0.0

    def _build_event_id(self, trigger_type: str, current_time: float) -> str:
        stamp = datetime.fromtimestamp(current_time, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = secrets.token_hex(2)
        return f"{self.camera_id}-{stamp}-{trigger_type}-{suffix}"

    def _build_payload(
        self,
        *,
        event_id: str,
        trigger_type: str,
        trigger_label: str,
        trigger_reason: str,
        confidence: float,
        current_time: float,
        hand_detected: bool,
        hand_confidence: float,
        voice_detected: bool,
        voice_confidence: float,
        gender_context: dict[str, Any] | None,
        frame_count: int | None,
        fps: float | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "eventId": event_id,
            "cameraId": self.camera_id,
            "triggerType": trigger_type,
            "triggerLabel": trigger_label,
            "triggerReason": trigger_reason,
            "triggerConfidence": round(float(confidence), 4),
            "frameTime": datetime.fromtimestamp(current_time, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": "backend_ml",
            "handDetected": hand_detected,
            "gestureConfidence": round(float(hand_confidence), 4),
            "voiceDetected": voice_detected,
            "voiceConfidence": round(float(voice_confidence), 4),
            "cooldownSeconds": self.cooldown_seconds,
            "modelVersions": self.model_versions,
        }

        if gender_context:
            payload["genderContext"] = gender_context

            for key in (
                "genderEnabled",
                "genderReady",
                "genderUpdated",
                "genderDetected",
                "genderEstimate",
                "genderEngine",
                "genderModelVersion",
                "faceModelVersion",
                "genderFrameSize",
                "genderSkippedReason",
                "genderEstimateLabel",
                "genderSource",
                "faceCount",
                "maleCount",
                "femaleCount",
                "unknownGenderCount",
                "rawFaceCount",
                "rawMaleCount",
                "rawFemaleCount",
                "rawUnknownGenderCount",
                "genderAverageFaceConfidence",
                "genderAverageConfidence",
                "genderAverageAge",
                "genderFaces",
            ):
                value = gender_context.get(key)
                if value is not None:
                    payload[key] = value

        if self.camera_name:
            payload["cameraName"] = self.camera_name
        if self.camera_location_label:
            payload["cameraLocationLabel"] = self.camera_location_label
        if frame_count is not None:
            payload["frameNumber"] = int(frame_count)
        if fps is not None:
            payload["fps"] = round(float(fps), 2)

        return payload

    def evaluate(
        self,
        *,
        current_time: float,
        hand_detected: bool = False,
        hand_confidence: float = 0.0,
        voice_detected: bool = False,
        voice_confidence: float = 0.0,
        gender_context: dict[str, Any] | None = None,
        frame_count: int | None = None,
        fps: float | None = None,
    ) -> AlertDecision:
        if self.is_in_cooldown(current_time):
            return AlertDecision(should_trigger=False, in_cooldown=True, cooldown_until=self.cooldown_until)

        hand_detected = bool(hand_detected)
        voice_detected = bool(voice_detected)
        hand_confidence = self._normalize_confidence(hand_confidence)
        voice_confidence = self._normalize_confidence(voice_confidence)

        if hand_detected:
            self.last_hand_detection_at = current_time
        if voice_detected:
            self.last_voice_detection_at = current_time

        if not hand_detected and not voice_detected:
            return AlertDecision(should_trigger=False, in_cooldown=False, cooldown_until=self.cooldown_until)

        trigger_type = ""
        trigger_label = ""
        trigger_reason = ""
        confidence = 0.0

        if hand_detected:
            trigger_type = "hand_gesture"
            trigger_label = "SOS"
            trigger_reason = f"Gesture (conf: {hand_confidence:.2f})"
            confidence = hand_confidence
        elif voice_detected:
            trigger_type = "voice_sos"
            trigger_label = "Voice SOS"
            trigger_reason = "Voice Command"
            confidence = voice_confidence or 1.0

        if self.enable_combined_trigger:
            combined_ready = False
            if hand_detected and voice_detected:
                combined_ready = True
            elif hand_detected and self.last_voice_detection_at is not None:
                combined_ready = (current_time - self.last_voice_detection_at) <= self.combined_window_seconds
            elif voice_detected and self.last_hand_detection_at is not None:
                combined_ready = (current_time - self.last_hand_detection_at) <= self.combined_window_seconds

            if combined_ready:
                trigger_type = "combined"
                trigger_label = "SOS + voice emergency"
                trigger_reason = "Hand SOS and voice emergency detected within 5 seconds"
                confidence = max(hand_confidence, voice_confidence, confidence)

        event_id = self._build_event_id(trigger_type, current_time)
        self.cooldown_until = current_time + self.cooldown_seconds

        payload = self._build_payload(
            event_id=event_id,
            trigger_type=trigger_type,
            trigger_label=trigger_label,
            trigger_reason=trigger_reason,
            confidence=confidence,
            current_time=current_time,
            hand_detected=hand_detected,
            hand_confidence=hand_confidence,
            voice_detected=voice_detected,
            voice_confidence=voice_confidence,
            gender_context=gender_context,
            frame_count=frame_count,
            fps=fps,
        )

        self.last_hand_detection_at = None
        self.last_voice_detection_at = None

        return AlertDecision(
            should_trigger=True,
            in_cooldown=False,
            trigger_type=trigger_type,
            trigger_label=trigger_label,
            trigger_reason=trigger_reason,
            confidence=confidence,
            event_id=event_id,
            payload=payload,
            cooldown_until=self.cooldown_until,
        )

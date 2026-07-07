"""High-level training wizard for the Phase 3 gesture experience."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Iterable

import cv2

from .landmarks import HandLandmarkExtractor
from .registry import activate_model
from .runtime import GestureRuntime
from .trainer import (
    collect_gesture_samples,
    load_dataset_samples,
    normalize_gesture_label,
    save_session_samples,
    train_and_activate_model,
)


@dataclass(slots=True)
class WizardPlanItem:
    label: str
    samples: int
    title: str
    guidance: str


NEGATIVE_GUIDANCE = [
    "Open palm",
    "Fist",
    "Pointing",
    "Phone holding",
    "Random hand movement",
    "Partial hand visible",
]


def build_training_plan(
    labels: Iterable[str],
    *,
    samples_per_label: int,
    negative_samples: int,
) -> list[WizardPlanItem]:
    plan: list[WizardPlanItem] = []
    for raw_label in labels:
        if not str(raw_label).strip():
            continue
        label = normalize_gesture_label(raw_label)
        target_samples = negative_samples if label == "_NEGATIVE" else samples_per_label
        guidance = "Hold the gesture steady and keep your hand fully visible."
        if label == "_NEGATIVE":
            guidance = "Show any non-SOS pose. Include open palm, fist, pointing, and partial hand views."
        plan.append(
            WizardPlanItem(
                label=label,
                samples=target_samples,
                title=f"Training {label}",
                guidance=guidance,
            )
        )
    return plan


def print_plan(plan: list[WizardPlanItem], logger=print) -> None:
    logger("=" * 72)
    logger("Phase 3 training wizard")
    logger("=" * 72)
    logger("Hotkeys during capture:")
    logger("  SPACE  pause/resume auto capture")
    logger("  R      restart current gesture capture")
    logger("  Q      quit wizard")
    logger("During preview:")
    logger("  T      start/stop test preview")
    logger("  A      activate model if metrics pass")
    logger("  Q      quit preview")
    logger("-" * 72)
    for index, item in enumerate(plan, start=1):
        logger(f"{index}. {item.label} -> {item.samples} samples")
        logger(f"   {item.guidance}")
    logger("-" * 72)


def _save_training_session(
    *,
    session_id: str,
    samples,
    label: str,
    camera_index: int,
    camera_backend_name: str,
) -> Path:
    return save_session_samples(
        session_id,
        samples,
        session_metadata={
            "gesture": label,
            "cameraIndex": camera_index,
            "cameraBackend": camera_backend_name,
            "wizardMode": True,
        },
    )


def run_training_wizard(
    cap: cv2.VideoCapture,
    *,
    plan: list[WizardPlanItem],
    display: bool,
    camera_index: int,
    camera_backend_name: str,
    min_quality: float,
    stabilization_frames: int,
    sample_stride: int,
    countdown_seconds: int,
    rotation_prompt_interval: int,
    n_neighbors: int,
    force: bool,
    preview_seconds: int,
    logger=print,
) -> dict[str, Any]:
    if not plan:
        raise ValueError("Training wizard requires at least one label")

    print_plan(plan, logger=logger)

    all_samples = []
    session_summaries: list[dict[str, Any]] = []

    for item in plan:
        logger("=" * 72)
        logger(f"{item.title} - {item.samples} samples")
        logger(item.guidance)
        if item.label == "_NEGATIVE":
            logger("Negative sample guide:")
            for hint in NEGATIVE_GUIDANCE:
                logger(f"  - {hint}")

        samples, session_id = collect_gesture_samples(
            cap,
            gesture=item.label,
            target_samples=item.samples,
            auto=True,
            min_quality=min_quality,
            stabilization_frames=stabilization_frames,
            sample_stride=sample_stride,
            display=display,
            window_name=f"Gesture Wizard - {item.label}",
            countdown_seconds=countdown_seconds,
            rotation_prompt_interval=rotation_prompt_interval,
            logger=logger,
        )
        session_dir = _save_training_session(
            session_id=session_id,
            samples=samples,
            label=item.label,
            camera_index=camera_index,
            camera_backend_name=camera_backend_name,
        )
        all_samples.extend(samples)
        session_summaries.append(
            {
                "gesture": item.label,
                "samples": len(samples),
                "sessionId": session_id,
                "sessionDir": str(session_dir),
            }
        )
        logger(f"[Wizard] Saved {item.label} session to {session_dir}")
        logger(f"[Wizard] Captured {len(samples)} samples for {item.label}")

    dataset_samples = load_dataset_samples()
    logger(f"[Wizard] Total dataset samples available: {len(dataset_samples)}")

    result = train_and_activate_model(
        dataset_samples,
        force=force,
        n_neighbors=n_neighbors,
        auto_activate=False,
    )

    report = result["report"]
    logger("=" * 72)
    logger(f"Model ID: {result['modelId']}")
    logger(f"Model Dir: {result['modelDir']}")
    logger(f"Accuracy: {report['accuracy']:.2%}")
    logger(f"Macro F1: {report['macro']['macro_f1']:.4f}")
    logger(f"Quality gate passed: {report['qualityGate']['passed']}")
    logger(f"Activation allowed: {report['activationAllowed']}")
    logger("=" * 72)

    preview_result = run_model_preview(
        cap,
        result["bundle"],
        report=report,
        display=display,
        preview_seconds=preview_seconds,
        logger=logger,
    )

    result["report"] = report
    result["sessionSummaries"] = session_summaries
    result["preview"] = preview_result
    result["allSamples"] = len(all_samples)
    return result


def run_model_preview(
    cap: cv2.VideoCapture,
    bundle,
    *,
    report: dict[str, Any],
    display: bool,
    preview_seconds: int,
    logger=print,
) -> dict[str, Any]:
    runtime = GestureRuntime(bundle=bundle, extractor=HandLandmarkExtractor(), refresh_interval_frames=999)
    preview_extractor = runtime.extractor
    activation_allowed = bool(report.get("activationAllowed"))
    testing = (not display) or preview_seconds <= 0
    activated = bool(report.get("activated"))
    start_time = monotonic()
    test_started_at: float | None = start_time if testing else None
    last_result: dict[str, Any] = {}

    logger("=" * 72)
    logger("Preview mode")
    logger("Press T to start/stop test preview.")
    if activation_allowed:
        logger("Press A to activate the model after preview.")
    else:
        logger("Activation is blocked by the quality gate.")
    logger("Press Q to finish.")
    logger("=" * 72)

    while True:
        success, frame = cap.read()
        if not success or frame is None:
            continue

        frame = cv2.flip(frame, 1)
        display_frame = frame.copy()
        fps = 0.0
        observation = preview_extractor.extract(frame)
        if observation is not None:
            preview_extractor.draw(display_frame, observation)

        result = runtime.detect(frame, fps=fps, observation=observation)
        last_result = {
            "confirmed": result.confirmed,
            "label": result.label,
            "confidence": result.confidence,
            "rawConfidence": result.raw_confidence,
            "qualityScore": result.quality_score,
            "triggerReason": result.trigger_reason,
        }

        cv2.putText(
            display_frame,
            "T test mode | A activate | Q quit",
            (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        if testing:
            label_text = result.label or "No gesture"
            cv2.putText(
                display_frame,
                f"Test: {label_text} | conf={result.confidence:.1%} | raw={result.raw_confidence:.1%}",
                (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
            )
            cv2.putText(
                display_frame,
                f"Quality={result.quality_score:.1%} | window={result.positive_count}/{result.window_count}",
                (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 0),
                2,
            )
            if result.confirmed:
                cv2.putText(
                    display_frame,
                    "SOS confirmed in preview",
                    (10, 135),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )

        if display:
            cv2.imshow("Gesture Wizard Preview", display_frame)
            key = cv2.waitKey(1) & 0xFF
        else:
            key = 0

        if key in {27, ord("q")}:
            break
        if key == ord("t"):
            testing = not testing
            test_started_at = monotonic() if testing else None
            logger("[Preview] Test mode enabled" if testing else "[Preview] Test mode paused")
        if key == ord("a"):
            if activation_allowed:
                activate_model(Path(bundle.model_dir), model_id=bundle.model_id)
                activated = True
                report["activated"] = True
                logger("[Preview] Model activated")
            else:
                logger("[Preview] Activation blocked by quality gate")

        if testing and preview_seconds > 0 and test_started_at is not None:
            if monotonic() - test_started_at >= preview_seconds:
                testing = False
                logger("[Preview] Test window completed")
                if not display:
                    break

        if not display and testing and preview_seconds <= 0:
            # Headless fallback: run a short deterministic preview window.
            if monotonic() - start_time >= 5.0:
                break

    if display:
        try:
            cv2.destroyWindow("Gesture Wizard Preview")
        except Exception:
            pass

    return {
        "activated": activated,
        "testing": testing,
        "lastResult": last_result,
    }

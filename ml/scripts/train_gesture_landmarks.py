#!/usr/bin/env python3
"""Capture landmark samples, train the gesture model, and activate it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2

from config import ENABLE_DISPLAY as CONFIG_ENABLE_DISPLAY, MAX_CAMERA_INDEX as CONFIG_MAX_CAMERA_INDEX
from pipelines.hand_gesture.registry import ensure_gesture_storage_layout
from pipelines.hand_gesture.wizard import build_training_plan, run_model_preview, run_training_wizard
from pipelines.hand_gesture.trainer import (
    collect_gesture_samples,
    load_dataset_samples,
    normalize_gesture_label,
    save_session_samples,
    train_and_activate_model,
)
from runtime.camera import configure_camera, find_camera, open_camera


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the SafeStree landmark gesture model")
    parser.add_argument("--gesture", help="Gesture label to record, e.g. SOS or HELP")
    parser.add_argument(
        "--wizard",
        action="store_true",
        help="Run the guided multi-step training wizard",
    )
    parser.add_argument(
        "--labels",
        default="SOS,NEGATIVE",
        help="Comma-separated labels for wizard mode (default: SOS,NEGATIVE)",
    )
    parser.add_argument("--samples", type=int, default=160, help="Number of samples to capture")
    parser.add_argument(
        "--negative-samples",
        type=int,
        default=250,
        help="Sample target for the NEGATIVE class in wizard mode",
    )
    parser.add_argument("--manual", action="store_true", help="Disable auto capture and use SPACE")
    parser.add_argument("--force", action="store_true", help="Activate even if quality gates fail")
    parser.add_argument(
        "--defer-activation",
        action="store_true",
        help="Save and preview the model before activating it",
    )
    parser.add_argument("--min-quality", type=float, default=0.60, help="Minimum quality threshold")
    parser.add_argument("--stabilization-frames", type=int, default=4, help="Stable frames before capture")
    parser.add_argument("--sample-stride", type=int, default=2, help="Frames between auto captures")
    parser.add_argument("--countdown-seconds", type=int, default=3, help="Countdown before each capture step")
    parser.add_argument(
        "--rotation-prompt-interval",
        type=int,
        default=30,
        help="Show the rotate-hand reminder after this many samples",
    )
    parser.add_argument("--n-neighbors", type=int, default=5, help="KNN neighbors")
    parser.add_argument(
        "--preview-seconds",
        type=int,
        default=12,
        help="Duration for the post-training test preview after pressing T",
    )
    parser.add_argument("--camera-index", type=int, default=None, help="Force a specific camera index")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Disable preview windows even if display support exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    display_enabled = bool(CONFIG_ENABLE_DISPLAY and not args.headless)
    auto_capture = not args.manual
    wizard_mode = bool(args.wizard)

    ensure_gesture_storage_layout()
    print("=" * 72)
    if wizard_mode:
        print("Gesture training wizard started")
        print("Mode: auto")
        print(f"Labels: {args.labels}")
        if args.manual:
            print("[WARN] Wizard mode always uses auto capture; --manual was ignored.")
    else:
        if not args.gesture:
            print("[ERROR] --gesture is required unless --wizard is used")
            return 1
        gesture_label = normalize_gesture_label(args.gesture)
        print(f"Gesture training started for: {gesture_label}")
        print(f"Mode: {'auto' if auto_capture else 'manual'}")
    print("=" * 72)

    camera_index, camera_backend_name, camera_backend = find_camera(
        max_camera_index=CONFIG_MAX_CAMERA_INDEX,
        forced_camera_index=str(args.camera_index) if args.camera_index is not None else None,
        logger=lambda message, prefix="INFO": print(f"[{prefix}] {message}"),
    )
    if camera_index == -1:
        print("[ERROR] No usable camera found")
        return 1

    cap = open_camera(camera_index, camera_backend)
    if not cap.isOpened():
        print("[ERROR] Could not open camera")
        return 1

    cap = configure_camera(cap)

    try:
        print(f"[INFO] Camera opened at index {camera_index} using {camera_backend_name}")

        if wizard_mode:
            plan = build_training_plan(
                args.labels.split(","),
                samples_per_label=args.samples,
                negative_samples=args.negative_samples,
            )
            result = run_training_wizard(
                cap,
                plan=plan,
                display=display_enabled,
                camera_index=camera_index,
                camera_backend_name=camera_backend_name,
                min_quality=args.min_quality,
                stabilization_frames=args.stabilization_frames,
                sample_stride=args.sample_stride,
                countdown_seconds=args.countdown_seconds,
                rotation_prompt_interval=args.rotation_prompt_interval,
                n_neighbors=args.n_neighbors,
                force=args.force,
                preview_seconds=args.preview_seconds,
                logger=print,
            )
            report = result["report"]
            if result["preview"]["activated"]:
                print("[INFO] Model activated from preview")
            elif report.get("activationAllowed"):
                print("[INFO] Model is ready for activation. Press A in preview or rerun with activation enabled.")
            else:
                print("[WARN] Model was saved but activation was blocked by quality gates.")
            return 0

        samples, session_id = collect_gesture_samples(
            cap,
            gesture=gesture_label,
            target_samples=args.samples,
            auto=auto_capture,
            min_quality=args.min_quality,
            stabilization_frames=args.stabilization_frames,
            sample_stride=args.sample_stride,
            display=display_enabled,
            window_name=f"Gesture Training - {gesture_label}",
            countdown_seconds=args.countdown_seconds,
            rotation_prompt_interval=args.rotation_prompt_interval,
            logger=print,
        )
        session_dir = save_session_samples(
            session_id,
            samples,
            session_metadata={
                "gesture": gesture_label,
                "mode": "auto" if auto_capture else "manual",
                "targetSamples": args.samples,
                "cameraIndex": camera_index,
                "cameraBackend": camera_backend_name,
            },
        )

        dataset_samples = load_dataset_samples()
        print(f"[INFO] Session saved to: {session_dir}")
        print(f"[INFO] Dataset sample count: {len(dataset_samples)}")

        result = train_and_activate_model(
            dataset_samples,
            force=args.force,
            n_neighbors=args.n_neighbors,
            auto_activate=not args.defer_activation,
        )

        report = result["report"]
        print("=" * 72)
        print(f"Model ID: {result['modelId']}")
        print(f"Model Dir: {result['modelDir']}")
        print(f"Activated: {result['activated']}")
        print(f"Activation allowed: {report.get('activationAllowed')}")
        print(f"Activation deferred: {report.get('activationDeferred')}")
        print(f"Accuracy: {report['accuracy']:.2%}")
        print(f"Macro F1: {report['macro']['macro_f1']:.4f}")
        print(f"Classes: {report['labels']}")
        print("=" * 72)

        if args.defer_activation and report.get("activationAllowed"):
            preview_result = run_model_preview(
                cap,
                result["bundle"],
                report=report,
                display=display_enabled,
                preview_seconds=args.preview_seconds,
                logger=print,
            )
            if preview_result["activated"]:
                print("[INFO] Model activated from preview")
            elif report.get("activationAllowed"):
                print("[INFO] Model is ready for activation. Use preview hotkey A to activate it.")
        elif not result["activated"] and not report.get("activationAllowed"):
            print("[WARN] Model saved but not activated because quality gates failed.")
            print("[WARN] Re-run with --force only if you intentionally want to activate it.")
        return 0
    finally:
        try:
            cap.release()
        except Exception:
            pass
        if display_enabled:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

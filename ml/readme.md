# Women's Safety System - ML Component

## Recent Updates

- Enhanced gesture recognition
- Organized directory structure
- Code cleanup
- Quality-based training
- Improved detection features
- Better performance and fewer false positives
- Phase 2 MediaPipe landmark runtime
- KNN training and evaluation scripts
- Phase 3 guided training wizard
- Phase 4 offline Vosk voice SOS
- Phase 5 OpenVINO gender estimate pipeline
- Phase 8 production hardening

## Project Structure

```text
backend/ml/
├── data/
│   ├── gestures/
│   ├── training_samples/
│   ├── images/
│   ├── cache/
│   └── logs/
├── config.py
├── runtime/
│   ├── camera.py
│   ├── event_aggregator.py
│   └── alert_dispatcher.py
├── pipelines/
│   ├── gender_detection/
│   │   ├── __init__.py
│   │   └── runtime.py
│   └── hand_gesture/
│       ├── classifier.py
│       ├── evaluator.py
│       ├── features.py
│       ├── landmarks.py
│       ├── registry.py
│       ├── runtime.py
│       ├── schemas.py
│       └── trainer.py
├── sos_gesture/
├── sos_voice/
├── get_location/
├── app.py
├── scripts/
│   ├── evaluate_gesture_landmarks.py
│   ├── setup_gender_models.py
│   ├── test_gesture_runtime.py
│   ├── test_gender_detection.py
│   ├── test_voice_sos.py
│   └── train_gesture_landmarks.py
├── train_gesture.py
├── quick_test.py
└── .env.example
```

## Documentation

- [QUICKSTART_FULL_PIPELINE.md](QUICKSTART_FULL_PIPELINE.md)
- [ENHANCEMENTS.md](ENHANCEMENTS.md)
- [GESTURE_DETECTION.md](GESTURE_DETECTION.md)

## Setup

### Prerequisites

- Python
- pip

### Create a virtual environment

```bash
python -m venv venv
```

### Activate it

```bash
.\venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Phase 0 Baseline Flags

Use [backend/ml/.env.example](.env.example) as the template for local configuration.

Recommended Phase 0 values:

```text
ENABLE_HAND_GESTURE=1
GESTURE_ENGINE=legacy_opencv
ENABLE_VOICE_SOS=1
VOICE_ENGINE=vosk
ENABLE_GENDER_DETECTION=0
GENDER_ENGINE=disabled
```

Rollback command for the current baseline:

```bash
ENABLE_HAND_GESTURE=1 GESTURE_ENGINE=legacy_opencv ENABLE_VOICE_SOS=0 ENABLE_GENDER_DETECTION=0 python app.py
```

Phase 0 keeps the current working behavior and only adds safe configuration switches.

If you use the internal ML route, the API service must also define
`INTERNAL_ML_SERVICE_TOKEN` from [backend/api/.env.example](../api/.env.example).

## Phase 1 Runtime Refactor

The main loop now pulls camera probing, alert aggregation, and alert dispatch
into `backend/ml/runtime/` while keeping `app.py` as the orchestrator.
This is a structural refactor only. Gesture and voice detection still use the
current OpenCV fallback and offline Vosk code paths.

## Phase 2 Gesture Upgrade

The new default hand gesture path is:

`MediaPipe Hand Landmarker -> 63-value landmark vector -> KNN classifier -> temporal confirmation -> SOS alert`

Use these commands after recording data:

```bash
python scripts/train_gesture_landmarks.py --gesture SOS --samples 160 --auto
python scripts/train_gesture_landmarks.py --gesture NEGATIVE --samples 160 --auto
python scripts/train_gesture_landmarks.py --gesture HELP --samples 160 --auto
python scripts/evaluate_gesture_landmarks.py
python scripts/test_gesture_runtime.py
```

Phase 2 keeps `app.py` backward compatible:

- If `GESTURE_ENGINE=mediapipe_landmark` and the active model is available, the new runtime is used.
- If the active landmark model is missing, `app.py` falls back to `legacy_opencv`.
- The alert payload now includes gesture model metadata when the new runtime is active.

## Phase 3 Training Wizard

Use this guided flow when you want a fast end-to-end training pass:

```bash
python scripts/train_gesture_landmarks.py --wizard --labels SOS,NEGATIVE --samples 160 --negative-samples 250
```

You can also include more labels:

```bash
python scripts/train_gesture_landmarks.py --wizard --labels SOS,HELP,NEGATIVE --samples 160 --negative-samples 250
```

Wizard hotkeys:

- `SPACE`: pause or resume auto capture
- `R`: restart the current gesture capture
- `T`: start or stop the post-training test preview
- `A`: activate the new model if metrics pass
- `Q`: quit

## Phase 4 Voice SOS Upgrade

The voice path is now offline-first:

`Microphone -> Vosk recognizer -> phrase matcher -> temporal confirmation -> voice SOS alert`

Download the model first if needed:

```bash
python scripts/download_vosk_model.py --language en
```

Use these checks after placing a Vosk model at `VOICE_MODEL_PATH`:

```bash
python scripts/test_voice_sos.py --offline
python app.py
```

Recommended voice config:

```text
ENABLE_VOICE_SOS=1
VOICE_ENGINE=vosk
VOICE_MODEL_PATH=data/models/voice/vosk-model-small-en-us
VOICE_CONFIRMATION_HITS=2
VOICE_CONFIRMATION_WINDOW_SECONDS=5
VOICE_TRIGGER_COOLDOWN_SECONDS=2
```

Voice matching is local and does not depend on Google speech APIs.

## Phase 5 Gender Estimate Upgrade

The scene gender estimate pipeline is local and optional:

`Camera frame -> OpenVINO face detection -> age/gender inference -> count smoothing -> estimated scene counts`

Use these commands after the OpenVINO models are downloaded:

```bash
python scripts/setup_gender_models.py
python scripts/test_gender_detection.py --offline
python app.py
```

Recommended gender config:

```text
ENABLE_GENDER_DETECTION=1
GENDER_ENGINE=openvino
GENDER_DEVICE=CPU
GENDER_MODEL_PATH=data/models/openvino/age-gender-recognition-retail-0013
FACE_MODEL_PATH=data/models/openvino/face-detection-retail-0004
GENDER_ANALYZE_EVERY_N_FRAMES=6
GENDER_SMOOTHING_WINDOW=5
GENDER_MAX_FACES=5
GENDER_CROP_MARGIN=0.15
GENDER_MIN_FACE_CONFIDENCE=0.40
GENDER_MIN_GENDER_CONFIDENCE=0.65
GENDER_USE_DEEPFACE_FALLBACK=1
```

The alert payload now carries estimated face, male, female, and unknown counts
from the ML side. The counts are clearly marked as estimates.

## Phase 8 Production Hardening

The runtime now adds:

- a persistent alert retry queue for confirmed SOS alerts
- a startup health report written to `STARTUP_HEALTH_REPORT_PATH`
- periodic FPS and latency logging
- graceful camera reconnect attempts
- privacy-safe snapshot retention
- integration tests for the hardening helpers

Useful configuration:

```text
ALERT_RETRY_QUEUE_DB_PATH=data/cache/alert_retry_queue.db
ALERT_RETRY_WORKER_INTERVAL_SECONDS=15
ALERT_RETRY_WORKER_BATCH_SIZE=5
ALERT_DISPATCH_MAX_ATTEMPTS=2
ALERT_IMAGE_RETENTION_DAYS=7
ALERT_RETENTION_SCAN_INTERVAL_SECONDS=300
STARTUP_HEALTH_REPORT_PATH=data/cache/startup_health_report.json
CAMERA_RECONNECT_MAX_ATTEMPTS=3
```

Run the phase 8 integration tests with:

```bash
python3 -m unittest discover -s tests -p "test_phase8_hardening.py"
```

## Run

```bash
python app.py
```

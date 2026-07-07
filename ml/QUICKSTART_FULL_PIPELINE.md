# SafeStree ML Quickstart

This is the simplest end-to-end guide for the SafeStree ML pipeline.

It covers:
- training a custom hand gesture
- using offline voice SOS
- enabling estimated gender detection
- running the full alert pipeline with the API and frontend

Assumptions:
- your webcam is already working
- your microphone is already working
- you are running the commands from `backend/ml`
- the project virtualenv exists at `backend/ml/venv`

## 1. What is trained and what is not

Only the hand gesture model is trained by you.

You do not train:
- voice SOS
- gender detection

Voice SOS uses offline phrase matching with Vosk.
Gender detection uses pre-trained local OpenVINO models.

## 2. Minimum config

Make sure these values are set in `backend/ml/.env` or copied from `.env.example`:

```text
ENABLE_HAND_GESTURE=1
GESTURE_ENGINE=mediapipe_landmark
GESTURE_TRIGGER_LABELS=SOS
ENABLE_VOICE_SOS=1
VOICE_ENGINE=vosk
VOICE_MODEL_PATH=data/models/voice/vosk-model-small-en-us
VOICE_TRIGGER_PHRASES=help me,please help,i need help,save me,i am in danger,bachao,madad
ENABLE_GENDER_DETECTION=1
GENDER_ENGINE=openvino
GENDER_DEVICE=CPU
GENDER_USE_DEEPFACE_FALLBACK=1
```

If the Vosk model folder is missing, voice SOS stays unavailable.
If the OpenVINO model files are missing, gender detection stays optional.

## 3. Train a hand gesture

Use the guided wizard first. It is the easiest way to get a working custom gesture.

```bash
./venv/bin/python scripts/train_gesture_landmarks.py --wizard --labels SOS,NEGATIVE --samples 160 --negative-samples 250
```

If you want a second positive gesture:

```bash
./venv/bin/python scripts/train_gesture_landmarks.py --wizard --labels SOS,HELP,NEGATIVE --samples 160 --negative-samples 250
```

If you want to train one custom stable pose directly:

```bash
./venv/bin/python scripts/train_gesture_landmarks.py --gesture STOP --samples 160 --auto
```

Training rules:
- keep the hand visible in the camera
- hold the pose steady
- capture negative samples too
- rotate the hand slightly when the wizard asks
- start with one emergency gesture plus one negative class

Good labels for this project:
- `SOS`
- `HELP`
- `STOP`
- any other stable, repeatable hand pose

Important:
- this model works best for static hand poses
- it does not learn long motion sequences like a video action model

## 4. Check the gesture model

Run the two local checks after training:

```bash
./venv/bin/python scripts/evaluate_gesture_landmarks.py
./venv/bin/python scripts/test_gesture_runtime.py
```

What success looks like:
- the model loads
- the trained label is predicted correctly
- `SOS` confirms only after several matching frames

## 5. Prepare voice SOS

Voice SOS is offline and simple.
You do not train a voice model here.

Make sure the Vosk model exists at:

```text
data/models/voice/vosk-model-small-en-us
```

Then run:

```bash
./venv/bin/python scripts/test_voice_sos.py --offline
```

If you want to change the phrases later, edit `VOICE_TRIGGER_PHRASES` in `.env`.

Recommended phrases:
- `help me`
- `please help`
- `i need help`
- `save me`
- `i am in danger`
- `bachao`
- `madad`

## 6. Prepare gender detection

Gender detection is also local and does not need training.

Run:

```bash
./venv/bin/python scripts/setup_gender_models.py
./venv/bin/python scripts/test_gender_detection.py --offline
```

What success looks like:
- faces are detected locally
- male/female/unknown counts are produced
- the UI receives counts marked as estimates

Important:
- this is an estimated scene count
- it is not identity verification

## 7. Run the full pipeline

Open three terminals.

Terminal 1: backend API

```bash
cd backend/api
npm run dev
```

Terminal 2: ML service

```bash
cd backend/ml
./venv/bin/python app.py
```

Terminal 3: frontend

```bash
cd frontend
npm run dev
```

Then open the app and test:
- hand gesture SOS
- voice SOS phrase
- gender estimate on the admin alert card
- alert sound on the admin panel

## 8. Simple test order

Use this order the first time:

1. Train `SOS` and `NEGATIVE`
2. Run `scripts/evaluate_gesture_landmarks.py`
3. Run `scripts/test_gesture_runtime.py`
4. Run `scripts/test_voice_sos.py --offline`
5. Run `scripts/setup_gender_models.py`
6. Run `scripts/test_gender_detection.py --offline`
7. Start `backend/api`
8. Start `backend/ml/app.py`
9. Start the frontend
10. Trigger a live SOS test

## 9. What a successful live test should do

When everything is working:
- the camera sees your hand gesture
- the gesture confirms after stable frames
- the voice listener recognizes an SOS phrase
- the gender pipeline counts faces on the camera frame
- one SOS alert is sent to the backend
- the admin panel shows the alert and plays the sound

## 10. If something is missing

Use this quick fallback list:

- Gesture model missing
  - rerun the training wizard
  - keep more negative samples

- Voice model missing
  - place the Vosk model in `data/models/voice/vosk-model-small-en-us`
  - rerun the voice offline test

- Gender model missing
  - rerun `scripts/setup_gender_models.py`
  - rerun the offline gender test

- Camera not opening
  - close other apps using the webcam
  - verify the OS camera permission

- Mic not picking up speech
  - check the OS microphone permission
  - confirm the correct input device is selected

## 11. Shortest working path

If you only want the fastest route:

1. Train `SOS` + `NEGATIVE`
2. Put the Vosk model in place
3. Download the OpenVINO gender models
4. Start the API
5. Start the ML service
6. Start the frontend
7. Trigger a test SOS

That is the simplest complete flow for SafeStree.

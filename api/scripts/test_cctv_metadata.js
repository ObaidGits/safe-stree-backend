import assert from "node:assert/strict";
import {
  buildCCTVAlertDocument,
  buildCCTVAlertLogContext,
} from "../utils/cctvAlertMetadata.js";

const facePayload = {
  bbox: { left: 1, top: 2, right: 3, bottom: 4 },
  faceConfidence: 0.88,
  genderLabel: "female",
  genderConfidence: 0.92,
  age: 29,
  ageConfidence: 0.77,
  source: "openvino",
  note: "primary face",
};

const alertDocument = buildCCTVAlertDocument({
  body: {
    longitude: "77.1025",
    latitude: "28.7041",
    accuracy: "12.5",
    eventId: "cam-main-01-20260706T120000Z-hand_gesture-abcd",
    triggerType: "hand_gesture",
    triggerLabel: "SOS",
    triggerReason: "Gesture (conf: 0.91)",
    triggerConfidence: "0.91",
    handDetected: "true",
    gestureLabel: "SOS",
    gestureRawConfidence: "0.95",
    gestureQualityScore: "0.88",
    gestureWindowCount: "7",
    gesturePositiveCount: "6",
    voiceDetected: "false",
    voiceConfidenceRaw: "0.81",
    genderEnabled: "true",
    genderReady: "true",
    genderDetected: "true",
    genderEstimate: "true",
    genderEngine: "openvino",
    genderModelVersion: "age-gender-recognition-retail-0013",
    faceModelVersion: "face-detection-retail-0004",
    faceCount: "2",
    maleCount: "1",
    femaleCount: "1",
    unknownGenderCount: "0",
    modelVersions: JSON.stringify({
      gesture: "knn_v3",
      voice: "vosk_v1",
      gender: "openvino_v2",
    }),
    genderContext: JSON.stringify({
      faceCount: 2,
      maleCount: 1,
      femaleCount: 1,
      unknownGenderCount: 0,
    }),
    genderFaces: JSON.stringify([facePayload]),
    ml: JSON.stringify({
      camera: {
        id: "cam-1",
        name: "Gate Cam",
        locationLabel: "Main Gate",
      },
      frame: {
        time: "2026-07-06T12:00:00Z",
        number: 42,
        fps: 24.5,
        size: [1920, 1080],
      },
      trigger: {
        type: "hand_gesture",
        label: "SOS",
        reason: "Gesture",
        confidence: 0.91,
      },
      gesture: {
        detected: true,
        label: "SOS",
        rawConfidence: 0.95,
        qualityScore: 0.88,
        windowCount: 7,
        positiveCount: 6,
        modelId: "gesture-v3",
        engine: "mediapipe",
        classifier: "knn",
      },
      voice: {
        detected: false,
        eventId: "voice-1",
        matchedPhrase: "help me",
        confidence: 0.81,
        recognitionConfidence: 0.74,
        engine: "vosk",
        modelVersion: "vosk-small-en-us",
      },
      gender: {
        enabled: true,
        ready: true,
        detected: true,
        estimate: true,
        engine: "openvino",
        modelVersion: "age-gender-recognition-retail-0013",
        faceModelVersion: "face-detection-retail-0004",
        faceCount: 2,
        maleCount: 1,
        femaleCount: 1,
        unknownGenderCount: 0,
        averageFaceConfidence: 0.88,
        averageGenderConfidence: 0.92,
        averageAge: 29,
        faces: [facePayload],
      },
    }),
  },
  savedFileName: "cctv_sos_123.jpg",
  ingestSource: "safe-stree-ml",
});

assert.equal(alertDocument.source, "CCTV");
assert.equal(alertDocument.ingestSource, "safe-stree-ml");
assert.equal(alertDocument.eventId, "cam-main-01-20260706T120000Z-hand_gesture-abcd");
assert.equal(alertDocument.triggerType, "hand_gesture");
assert.equal(alertDocument.triggerConfidence, 0.91);
assert.equal(alertDocument.gestureConfidence, 0.95);
assert.equal(alertDocument.voiceConfidence, 0.81);
assert.equal(alertDocument.faceCount, 2);
assert.equal(alertDocument.maleCount, 1);
assert.equal(alertDocument.femaleCount, 1);
assert.equal(alertDocument.ml.schemaVersion, "2026-07-06");
assert.equal(alertDocument.ml.camera.name, "Gate Cam");
assert.equal(alertDocument.ml.frame.number, 42);
assert.equal(alertDocument.ml.gesture.classifier, "knn");
assert.equal(alertDocument.ml.voice.modelVersion, "vosk-small-en-us");
assert.equal(alertDocument.ml.gender.faces[0].genderLabel, "female");
assert.equal(alertDocument.ml.rawGenderContext.faceCount, 2);
assert.equal(alertDocument.ml.rawPayload.camera.locationLabel, "Main Gate");
assert.equal(alertDocument.modelVersions.gender, "openvino_v2");

const logContext = buildCCTVAlertLogContext(alertDocument);
assert.equal(logContext.eventId, alertDocument.eventId);
assert.equal(logContext.cameraId, "cam-1");
assert.equal(logContext.gesture.classifier, "knn");
assert.equal(logContext.voiceDetails.engine, "vosk");
assert.equal(logContext.gender.faceCount, 2);
assert.equal(logContext.mlSchemaVersion, "2026-07-06");
assert.equal(logContext.context, undefined);

const nestedLocationDocument = buildCCTVAlertDocument({
  body: {
    ml: JSON.stringify({
      location: {
        coordinates: [10.5, 20.25],
        accuracy: 3.2,
      },
      eventId: "nested-location-001",
    }),
  },
  savedFileName: "nested_location.jpg",
});

assert.equal(nestedLocationDocument.eventId, "nested-location-001");
assert.equal(nestedLocationDocument.location.coordinates[0], 10.5);
assert.equal(nestedLocationDocument.location.coordinates[1], 20.25);
assert.equal(nestedLocationDocument.location.accuracy, 3.2);

console.log("CCTV metadata normalization smoke test passed");

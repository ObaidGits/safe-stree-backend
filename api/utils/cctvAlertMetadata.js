import fs from "fs/promises";
import path from "path";

const ALERT_SCHEMA_VERSION = "2026-07-06";
const CCTV_IMAGE_DIR = path.resolve("public/cctv_sos");

const hasValue = (value) =>
  value !== undefined &&
  value !== null &&
  !(typeof value === "string" && value.trim() === "");

const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const firstDefined = (...values) => values.find((value) => hasValue(value));

export const parseMaybeJson = (value) => {
  if (!hasValue(value)) {
    return undefined;
  }

  if (isPlainObject(value) || Array.isArray(value)) {
    return value;
  }

  if (typeof value !== "string") {
    return value;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  const looksJson =
    trimmed === "null" ||
    trimmed === "true" ||
    trimmed === "false" ||
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"));

  if (!looksJson) {
    return trimmed;
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
};

export const parseMaybeString = (value, maxLength = 256) => {
  if (!hasValue(value)) {
    return undefined;
  }

  if (typeof value !== "string") {
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    return undefined;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  return trimmed.slice(0, Math.max(1, maxLength));
};

export const parseMaybeNumber = (value, options = {}) => {
  if (!hasValue(value)) {
    return undefined;
  }

  const { min = Number.NEGATIVE_INFINITY, max = Number.POSITIVE_INFINITY, integer = false } = options;
  const parsed = typeof value === "number" ? value : Number.parseFloat(String(value).trim());

  if (!Number.isFinite(parsed)) {
    return undefined;
  }

  const normalized = integer ? Math.round(parsed) : parsed;
  return Math.min(max, Math.max(min, normalized));
};

export const parseMaybeBoolean = (value) => {
  if (!hasValue(value)) {
    return undefined;
  }

  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "number") {
    return value !== 0;
  }

  if (typeof value !== "string") {
    return undefined;
  }

  const normalized = value.trim().toLowerCase();
  if (["true", "1", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["false", "0", "no", "off"].includes(normalized)) {
    return false;
  }

  return undefined;
};

const parseMaybeObject = (value) => {
  const parsed = parseMaybeJson(value);
  return isPlainObject(parsed) ? parsed : undefined;
};

const parseMaybeArray = (value) => {
  const parsed = parseMaybeJson(value);
  return Array.isArray(parsed) ? parsed : undefined;
};

const normalizeNumberList = (values, options = {}) => {
  const parsedValues = Array.isArray(values) ? values : [];
  const numbers = parsedValues
    .map((entry) => parseMaybeNumber(entry, options))
    .filter((entry) => entry !== undefined);

  return numbers.length ? numbers : undefined;
};

const normalizeGenderFace = (face) => {
  if (!isPlainObject(face)) {
    return undefined;
  }

  const bbox = isPlainObject(face.bbox)
    ? {
        left: parseMaybeNumber(face.bbox.left, { integer: true, min: 0 }),
        top: parseMaybeNumber(face.bbox.top, { integer: true, min: 0 }),
        right: parseMaybeNumber(face.bbox.right, { integer: true, min: 0 }),
        bottom: parseMaybeNumber(face.bbox.bottom, { integer: true, min: 0 }),
      }
    : undefined;

  return {
    bbox,
    faceConfidence: parseMaybeNumber(face.faceConfidence, { min: 0, max: 1 }),
    genderLabel: parseMaybeString(face.genderLabel, 32),
    genderConfidence: parseMaybeNumber(face.genderConfidence, { min: 0, max: 1 }),
    age: parseMaybeNumber(face.age, { min: 0, max: 120 }),
    ageConfidence: parseMaybeNumber(face.ageConfidence, { min: 0, max: 1 }),
    source: parseMaybeString(face.source, 32),
    note: parseMaybeString(face.note, 160),
  };
};

const normalizeGenderFaces = (value) => {
  const faces = parseMaybeArray(value);
  if (!faces) {
    return undefined;
  }

  const normalizedFaces = faces
    .map((face) => normalizeGenderFace(face))
    .filter(Boolean)
    .slice(0, 10);

  return normalizedFaces.length ? normalizedFaces : undefined;
};

const normalizeStringMap = (value, maxEntries = 16, maxLength = 64) => {
  const parsed = parseMaybeObject(value);
  if (!parsed) {
    return undefined;
  }

  const normalized = {};
  for (const [key, rawValue] of Object.entries(parsed).slice(0, maxEntries)) {
    const cleanKey = parseMaybeString(key, 64);
    const cleanValue = parseMaybeString(rawValue, maxLength);
    if (cleanKey && cleanValue !== undefined) {
      normalized[cleanKey] = cleanValue;
    }
  }

  return Object.keys(normalized).length ? normalized : undefined;
};

const buildCameraSection = (body, mlPayload) => {
  const mlCamera = isPlainObject(mlPayload?.camera) ? mlPayload.camera : {};
  const id = parseMaybeString(
    firstDefined(body.cameraId, body.camera_id, mlCamera.id, mlCamera.cameraId),
    128
  );
  const name = parseMaybeString(
    firstDefined(body.cameraName, body.camera_name, mlCamera.name, mlCamera.cameraName),
    128
  );
  const locationLabel = parseMaybeString(
    firstDefined(
      body.cameraLocationLabel,
      body.camera_location_label,
      mlCamera.locationLabel,
      mlCamera.cameraLocationLabel
    ),
    160
  );

  const camera = {};
  if (id !== undefined) camera.id = id;
  if (name !== undefined) camera.name = name;
  if (locationLabel !== undefined) camera.locationLabel = locationLabel;
  return camera;
};

const buildFrameSection = (body, mlPayload) => {
  const mlFrame = isPlainObject(mlPayload?.frame) ? mlPayload.frame : {};
  const frameTime = parseMaybeString(
    firstDefined(body.frameTime, body.frame_time, mlFrame.time, mlFrame.frameTime),
    64
  );
  const frameNumber = parseMaybeNumber(
    firstDefined(body.frameNumber, body.frame_number, mlFrame.number, mlFrame.frameNumber),
    { integer: true, min: 0 }
  );
  const fps = parseMaybeNumber(firstDefined(body.fps, mlFrame.fps), { min: 0 });
  const frameSize = parseMaybeArray(
    firstDefined(body.genderFrameSize, body.gender_frame_size, mlFrame.size, mlFrame.frameSize)
  );

  const frame = {};
  if (frameTime !== undefined) frame.time = frameTime;
  if (frameNumber !== undefined) frame.number = frameNumber;
  if (fps !== undefined) frame.fps = Math.round(fps * 100) / 100;
  if (frameSize?.length) {
    const normalizedFrameSize = normalizeNumberList(frameSize, { integer: true, min: 0 });
    if (normalizedFrameSize?.length) {
      frame.size = normalizedFrameSize.slice(0, 2);
    }
  }

  return frame;
};

const buildTriggerSection = (body, mlPayload) => {
  const mlTrigger = isPlainObject(mlPayload?.trigger) ? mlPayload.trigger : {};
  const type = parseMaybeString(firstDefined(body.triggerType, mlTrigger.type), 64);
  const label = parseMaybeString(firstDefined(body.triggerLabel, mlTrigger.label), 128);
  const reason = parseMaybeString(firstDefined(body.triggerReason, mlTrigger.reason), 256);
  const confidence = parseMaybeNumber(
    firstDefined(body.triggerConfidence, mlTrigger.confidence),
    { min: 0, max: 1 }
  );

  const trigger = {};
  if (type !== undefined) trigger.type = type;
  if (label !== undefined) trigger.label = label;
  if (reason !== undefined) trigger.reason = reason;
  if (confidence !== undefined) trigger.confidence = confidence;
  return trigger;
};

const buildGestureSection = (body, mlPayload) => {
  const mlGesture = isPlainObject(mlPayload?.gesture) ? mlPayload.gesture : {};
  const detected = parseMaybeBoolean(firstDefined(body.handDetected, mlGesture.detected));
  const label = parseMaybeString(firstDefined(body.gestureLabel, mlGesture.label), 64);
  const rawConfidence = parseMaybeNumber(
    firstDefined(body.gestureRawConfidence, body.gestureConfidence, mlGesture.rawConfidence),
    { min: 0, max: 1 }
  );
  const qualityScore = parseMaybeNumber(
    firstDefined(body.gestureQualityScore, mlGesture.qualityScore),
    { min: 0, max: 1 }
  );
  const windowCount = parseMaybeNumber(
    firstDefined(body.gestureWindowCount, mlGesture.windowCount),
    { integer: true, min: 0 }
  );
  const positiveCount = parseMaybeNumber(
    firstDefined(body.gesturePositiveCount, mlGesture.positiveCount),
    { integer: true, min: 0 }
  );
  const modelId = parseMaybeString(firstDefined(body.gestureModelId, mlGesture.modelId), 128);
  const modelDir = parseMaybeString(firstDefined(body.gestureModelDir, mlGesture.modelDir), 256);
  const engine = parseMaybeString(firstDefined(body.gestureEngine, mlGesture.engine), 64);
  const classifier = parseMaybeString(firstDefined(body.gestureClassifier, mlGesture.classifier), 64);

  const gesture = {};
  if (detected !== undefined) gesture.detected = detected;
  if (label !== undefined) gesture.label = label;
  if (rawConfidence !== undefined) gesture.rawConfidence = rawConfidence;
  if (qualityScore !== undefined) gesture.qualityScore = qualityScore;
  if (windowCount !== undefined) gesture.windowCount = windowCount;
  if (positiveCount !== undefined) gesture.positiveCount = positiveCount;
  if (modelId !== undefined) gesture.modelId = modelId;
  if (modelDir !== undefined) gesture.modelDir = modelDir;
  if (engine !== undefined) gesture.engine = engine;
  if (classifier !== undefined) gesture.classifier = classifier;
  return gesture;
};

const buildVoiceSection = (body, mlPayload) => {
  const mlVoice = isPlainObject(mlPayload?.voice) ? mlPayload.voice : {};
  const detected = parseMaybeBoolean(firstDefined(body.voiceDetected, mlVoice.detected));
  const eventId = parseMaybeString(firstDefined(body.voiceEventId, mlVoice.eventId), 200);
  const transcript = parseMaybeString(firstDefined(body.voiceTranscript, mlVoice.transcript), 400);
  const matchedPhrase = parseMaybeString(
    firstDefined(body.voiceMatchedPhrase, mlVoice.matchedPhrase),
    200
  );
  const matchKind = parseMaybeString(firstDefined(body.voiceMatchKind, mlVoice.matchKind), 64);
  const source = parseMaybeString(firstDefined(body.voiceSource, mlVoice.source), 64);
  const modelVersion = parseMaybeString(
    firstDefined(body.voiceModelVersion, mlVoice.modelVersion),
    128
  );
  const engine = parseMaybeString(firstDefined(body.voiceEngine, mlVoice.engine), 64);
  const confidence = parseMaybeNumber(firstDefined(body.voiceConfidenceRaw, body.voiceConfidence), {
    min: 0,
    max: 1,
  });
  const recognitionConfidence = parseMaybeNumber(
    firstDefined(body.voiceRecognitionConfidence, mlVoice.recognitionConfidence),
    { min: 0, max: 1 }
  );

  const voice = {};
  if (detected !== undefined) voice.detected = detected;
  if (eventId !== undefined) voice.eventId = eventId;
  if (transcript !== undefined) voice.transcript = transcript;
  if (matchedPhrase !== undefined) voice.matchedPhrase = matchedPhrase;
  if (matchKind !== undefined) voice.matchKind = matchKind;
  if (source !== undefined) voice.source = source;
  if (modelVersion !== undefined) voice.modelVersion = modelVersion;
  if (engine !== undefined) voice.engine = engine;
  if (confidence !== undefined) voice.confidence = confidence;
  if (recognitionConfidence !== undefined) voice.recognitionConfidence = recognitionConfidence;
  return voice;
};

const buildGenderSection = (body, mlPayload) => {
  const mlGender = isPlainObject(mlPayload?.gender) ? mlPayload.gender : {};
  const enabled = parseMaybeBoolean(firstDefined(body.genderEnabled, mlGender.enabled));
  const ready = parseMaybeBoolean(firstDefined(body.genderReady, mlGender.ready));
  const updated = parseMaybeBoolean(firstDefined(body.genderUpdated, mlGender.updated));
  const detected = parseMaybeBoolean(firstDefined(body.genderDetected, mlGender.detected));
  const estimate = parseMaybeBoolean(firstDefined(body.genderEstimate, mlGender.estimate));
  const engine = parseMaybeString(firstDefined(body.genderEngine, mlGender.engine), 64);
  const modelVersion = parseMaybeString(firstDefined(body.genderModelVersion, mlGender.modelVersion), 128);
  const faceModelVersion = parseMaybeString(
    firstDefined(body.faceModelVersion, mlGender.faceModelVersion),
    128
  );
  const frameSize = parseMaybeArray(firstDefined(body.genderFrameSize, mlGender.frameSize));
  const skippedReason = parseMaybeString(
    firstDefined(body.genderSkippedReason, mlGender.skippedReason),
    256
  );
  const estimateLabel = parseMaybeString(
    firstDefined(body.genderEstimateLabel, mlGender.estimateLabel),
    64
  );
  const source = parseMaybeString(firstDefined(body.genderSource, mlGender.source), 64);
  const faceCount = parseMaybeNumber(firstDefined(body.faceCount, mlGender.faceCount), {
    integer: true,
    min: 0,
  });
  const maleCount = parseMaybeNumber(firstDefined(body.maleCount, mlGender.maleCount), {
    integer: true,
    min: 0,
  });
  const femaleCount = parseMaybeNumber(firstDefined(body.femaleCount, mlGender.femaleCount), {
    integer: true,
    min: 0,
  });
  const unknownGenderCount = parseMaybeNumber(
    firstDefined(body.unknownGenderCount, mlGender.unknownGenderCount),
    { integer: true, min: 0 }
  );
  const rawFaceCount = parseMaybeNumber(firstDefined(body.rawFaceCount, mlGender.rawFaceCount), {
    integer: true,
    min: 0,
  });
  const rawMaleCount = parseMaybeNumber(firstDefined(body.rawMaleCount, mlGender.rawMaleCount), {
    integer: true,
    min: 0,
  });
  const rawFemaleCount = parseMaybeNumber(firstDefined(body.rawFemaleCount, mlGender.rawFemaleCount), {
    integer: true,
    min: 0,
  });
  const rawUnknownGenderCount = parseMaybeNumber(
    firstDefined(body.rawUnknownGenderCount, mlGender.rawUnknownGenderCount),
    { integer: true, min: 0 }
  );
  const averageFaceConfidence = parseMaybeNumber(
    firstDefined(body.genderAverageFaceConfidence, mlGender.averageFaceConfidence),
    { min: 0, max: 1 }
  );
  const averageGenderConfidence = parseMaybeNumber(
    firstDefined(body.genderAverageConfidence, mlGender.averageGenderConfidence),
    { min: 0, max: 1 }
  );
  const averageAge = parseMaybeNumber(firstDefined(body.genderAverageAge, mlGender.averageAge), {
    min: 0,
    max: 120,
  });
  const faces = normalizeGenderFaces(firstDefined(body.genderFaces, mlGender.faces));

  const gender = {};
  if (enabled !== undefined) gender.enabled = enabled;
  if (ready !== undefined) gender.ready = ready;
  if (updated !== undefined) gender.updated = updated;
  if (detected !== undefined) gender.detected = detected;
  if (estimate !== undefined) gender.estimate = estimate;
  if (engine !== undefined) gender.engine = engine;
  if (modelVersion !== undefined) gender.modelVersion = modelVersion;
  if (faceModelVersion !== undefined) gender.faceModelVersion = faceModelVersion;
  if (frameSize?.length) gender.frameSize = frameSize.slice(0, 2);
  if (skippedReason !== undefined) gender.skippedReason = skippedReason;
  if (estimateLabel !== undefined) gender.estimateLabel = estimateLabel;
  if (source !== undefined) gender.source = source;
  if (faceCount !== undefined) gender.faceCount = faceCount;
  if (maleCount !== undefined) gender.maleCount = maleCount;
  if (femaleCount !== undefined) gender.femaleCount = femaleCount;
  if (unknownGenderCount !== undefined) gender.unknownGenderCount = unknownGenderCount;
  if (rawFaceCount !== undefined) gender.rawFaceCount = rawFaceCount;
  if (rawMaleCount !== undefined) gender.rawMaleCount = rawMaleCount;
  if (rawFemaleCount !== undefined) gender.rawFemaleCount = rawFemaleCount;
  if (rawUnknownGenderCount !== undefined) gender.rawUnknownGenderCount = rawUnknownGenderCount;
  if (averageFaceConfidence !== undefined) gender.averageFaceConfidence = averageFaceConfidence;
  if (averageGenderConfidence !== undefined) gender.averageGenderConfidence = averageGenderConfidence;
  if (averageAge !== undefined) gender.averageAge = averageAge;
  if (faces !== undefined) gender.faces = faces;
  return gender;
};

export const buildCCTVAlertDocument = ({
  body = {},
  savedFileName,
  defaultSource = "CCTV",
  ingestSource = "",
}) => {
  const mlPayload = parseMaybeObject(body.ml);
  const mlLocation = isPlainObject(mlPayload?.location) ? mlPayload.location : {};
  const mlCoordinates = Array.isArray(mlLocation.coordinates) ? mlLocation.coordinates : [];
  const eventId = parseMaybeString(
    firstDefined(body.eventId, body.event_id, mlPayload?.eventId, mlPayload?.event_id),
    200
  );
  const source = defaultSource;
  const resolvedIngestSource = parseMaybeString(
    firstDefined(ingestSource, body.ingestSource, body.source, mlPayload?.source),
    64
  );
  const location = {
    type: "Point",
    coordinates: [
      parseMaybeNumber(
        firstDefined(body.longitude, mlLocation.longitude, mlLocation.lng, mlCoordinates[0]),
        { min: -180, max: 180 }
      ),
      parseMaybeNumber(
        firstDefined(body.latitude, mlLocation.latitude, mlLocation.lat, mlCoordinates[1]),
        { min: -90, max: 90 }
      ),
    ],
    accuracy: parseMaybeNumber(firstDefined(body.accuracy, mlLocation.accuracy), { min: 0 }),
  };

  const modelVersions = normalizeStringMap(
    firstDefined(body.modelVersions, body.model_versions, mlPayload?.modelVersions, mlPayload?.model_versions)
  );
  const genderContext = parseMaybeObject(
    firstDefined(body.genderContext, body.gender_context, mlPayload?.genderContext, mlPayload?.gender_context)
  );
  const mlCamera = buildCameraSection(body, mlPayload);
  const mlFrame = buildFrameSection(body, mlPayload);
  const mlTrigger = buildTriggerSection(body, mlPayload);
  const mlGesture = buildGestureSection(body, mlPayload);
  const mlVoice = buildVoiceSection(body, mlPayload);
  const mlGender = buildGenderSection(body, mlPayload);

  const ml = {
    schemaVersion: ALERT_SCHEMA_VERSION,
    source: resolvedIngestSource || source,
  };

  if (Object.keys(mlCamera).length) ml.camera = mlCamera;
  if (Object.keys(mlFrame).length) ml.frame = mlFrame;
  if (Object.keys(mlTrigger).length) ml.trigger = mlTrigger;
  if (Object.keys(mlGesture).length) ml.gesture = mlGesture;
  if (Object.keys(mlVoice).length) ml.voice = mlVoice;
  if (Object.keys(mlGender).length) ml.gender = mlGender;
  if (modelVersions) ml.modelVersions = modelVersions;
  if (genderContext) ml.rawGenderContext = genderContext;
  if (mlPayload) ml.rawPayload = mlPayload;

  const triggerConfidence = parseMaybeNumber(
    firstDefined(body.triggerConfidence, mlTrigger.confidence),
    { min: 0, max: 1 }
  );
  const gestureConfidence = parseMaybeNumber(
    firstDefined(body.gestureRawConfidence, body.gestureConfidence, mlGesture.rawConfidence),
    {
      min: 0,
      max: 1,
    }
  );
  const voiceConfidence = parseMaybeNumber(
    firstDefined(body.voiceConfidenceRaw, body.voiceConfidence, mlVoice.confidence, mlVoice.recognitionConfidence),
    { min: 0, max: 1 }
  );
  const genderCounts = {
    faceCount: mlGender.faceCount,
    maleCount: mlGender.maleCount,
    femaleCount: mlGender.femaleCount,
    unknownGenderCount: mlGender.unknownGenderCount,
  };

  const document = {
    location,
    sos_img: savedFileName,
    eventId,
    source,
    ingestSource: resolvedIngestSource || undefined,
    cameraId: mlCamera.id,
    cameraName: mlCamera.name,
    cameraLocationLabel: mlCamera.locationLabel,
    frameTime: mlFrame.time,
    frameNumber: mlFrame.number,
    fps: mlFrame.fps,
    triggerType: mlTrigger.type,
    triggerLabel: mlTrigger.label,
    triggerReason: mlTrigger.reason,
    triggerConfidence,
    handDetected: mlGesture.detected,
    gestureLabel: mlGesture.label,
    gestureConfidence,
    voiceDetected: mlVoice.detected,
    voiceEventId: mlVoice.eventId,
    voiceMatchedPhrase: mlVoice.matchedPhrase,
    voiceConfidence,
    genderEnabled: mlGender.enabled,
    genderReady: mlGender.ready,
    genderDetected: mlGender.detected,
    genderEstimate: mlGender.estimate,
    genderEngine: mlGender.engine,
    genderModelVersion: mlGender.modelVersion,
    faceModelVersion: mlGender.faceModelVersion,
    faceCount: genderCounts.faceCount,
    maleCount: genderCounts.maleCount,
    femaleCount: genderCounts.femaleCount,
    unknownGenderCount: genderCounts.unknownGenderCount,
    modelVersions: modelVersions || {},
    ml,
  };

  return document;
};

export const buildCCTVAlertLogContext = (document) => {
  const gender = document.ml?.gender || {};
  const gesture = document.ml?.gesture || {};
  const voice = document.ml?.voice || {};

  return {
    eventId: document.eventId || null,
    source: document.source || null,
    ingestSource: document.ingestSource || null,
    cameraId: document.cameraId || null,
    cameraName: document.cameraName || null,
    triggerType: document.triggerType || null,
    triggerLabel: document.triggerLabel || null,
    triggerConfidence: document.triggerConfidence ?? null,
    frameTime: document.frameTime || null,
    frameNumber: document.frameNumber ?? null,
    fps: document.fps ?? null,
    handDetected: document.handDetected ?? null,
    gestureLabel: document.gestureLabel || null,
    gestureConfidence: document.gestureConfidence ?? null,
    voiceDetected: document.voiceDetected ?? null,
    voiceEventId: document.voiceEventId || null,
    voiceMatchedPhrase: document.voiceMatchedPhrase || null,
    voiceConfidence: document.voiceConfidence ?? null,
    gender: {
      enabled: gender.enabled ?? null,
      ready: gender.ready ?? null,
      detected: gender.detected ?? null,
      engine: gender.engine || null,
      modelVersion: gender.modelVersion || null,
      faceModelVersion: gender.faceModelVersion || null,
      faceCount: gender.faceCount ?? null,
      maleCount: gender.maleCount ?? null,
      femaleCount: gender.femaleCount ?? null,
      unknownGenderCount: gender.unknownGenderCount ?? null,
      averageGenderConfidence: gender.averageGenderConfidence ?? null,
    },
    mlSchemaVersion: document.ml?.schemaVersion || null,
    gesture: {
      label: gesture.label || null,
      rawConfidence: gesture.rawConfidence ?? null,
      qualityScore: gesture.qualityScore ?? null,
      windowCount: gesture.windowCount ?? null,
      positiveCount: gesture.positiveCount ?? null,
      engine: gesture.engine || null,
      classifier: gesture.classifier || null,
    },
    voiceDetails: {
      transcript: voice.transcript || null,
      matchedPhrase: voice.matchedPhrase || null,
      matchKind: voice.matchKind || null,
      engine: voice.engine || null,
      modelVersion: voice.modelVersion || null,
    },
  };
};

export const buildCCTVImagePath = (savedFileName) =>
  savedFileName ? path.join(CCTV_IMAGE_DIR, savedFileName) : "";

export const removeCCTVImage = async (savedFileName) => {
  const imagePath = buildCCTVImagePath(savedFileName);
  if (!imagePath) {
    return;
  }

  try {
    await fs.unlink(imagePath);
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }
};

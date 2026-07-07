import mongoose from "mongoose";

const cctvFaceEvidenceSchema = new mongoose.Schema(
  {
    bbox: {
      left: { type: Number, default: undefined },
      top: { type: Number, default: undefined },
      right: { type: Number, default: undefined },
      bottom: { type: Number, default: undefined },
    },
    faceConfidence: { type: Number, default: undefined },
    genderLabel: { type: String, trim: true, default: undefined },
    genderConfidence: { type: Number, default: undefined },
    age: { type: Number, default: undefined },
    ageConfidence: { type: Number, default: undefined },
    source: { type: String, trim: true, default: undefined },
    note: { type: String, trim: true, default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvCameraEvidenceSchema = new mongoose.Schema(
  {
    id: { type: String, trim: true, default: undefined },
    name: { type: String, trim: true, default: undefined },
    locationLabel: { type: String, trim: true, default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvFrameEvidenceSchema = new mongoose.Schema(
  {
    time: { type: String, trim: true, default: undefined },
    number: { type: Number, default: undefined },
    fps: { type: Number, default: undefined },
    size: { type: [Number], default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvTriggerEvidenceSchema = new mongoose.Schema(
  {
    type: { type: String, trim: true, default: undefined },
    label: { type: String, trim: true, default: undefined },
    reason: { type: String, trim: true, default: undefined },
    confidence: { type: Number, default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvGestureEvidenceSchema = new mongoose.Schema(
  {
    detected: { type: Boolean, default: undefined },
    label: { type: String, trim: true, default: undefined },
    rawConfidence: { type: Number, default: undefined },
    qualityScore: { type: Number, default: undefined },
    windowCount: { type: Number, default: undefined },
    positiveCount: { type: Number, default: undefined },
    modelId: { type: String, trim: true, default: undefined },
    modelDir: { type: String, trim: true, default: undefined },
    engine: { type: String, trim: true, default: undefined },
    classifier: { type: String, trim: true, default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvVoiceEvidenceSchema = new mongoose.Schema(
  {
    detected: { type: Boolean, default: undefined },
    eventId: { type: String, trim: true, default: undefined },
    transcript: { type: String, trim: true, default: undefined },
    matchedPhrase: { type: String, trim: true, default: undefined },
    matchKind: { type: String, trim: true, default: undefined },
    source: { type: String, trim: true, default: undefined },
    modelVersion: { type: String, trim: true, default: undefined },
    engine: { type: String, trim: true, default: undefined },
    confidence: { type: Number, default: undefined },
    recognitionConfidence: { type: Number, default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvGenderEvidenceSchema = new mongoose.Schema(
  {
    enabled: { type: Boolean, default: undefined },
    ready: { type: Boolean, default: undefined },
    updated: { type: Boolean, default: undefined },
    detected: { type: Boolean, default: undefined },
    estimate: { type: Boolean, default: undefined },
    engine: { type: String, trim: true, default: undefined },
    modelVersion: { type: String, trim: true, default: undefined },
    faceModelVersion: { type: String, trim: true, default: undefined },
    frameSize: { type: [Number], default: undefined },
    skippedReason: { type: String, trim: true, default: undefined },
    estimateLabel: { type: String, trim: true, default: undefined },
    source: { type: String, trim: true, default: undefined },
    faceCount: { type: Number, default: undefined },
    maleCount: { type: Number, default: undefined },
    femaleCount: { type: Number, default: undefined },
    unknownGenderCount: { type: Number, default: undefined },
    rawFaceCount: { type: Number, default: undefined },
    rawMaleCount: { type: Number, default: undefined },
    rawFemaleCount: { type: Number, default: undefined },
    rawUnknownGenderCount: { type: Number, default: undefined },
    averageFaceConfidence: { type: Number, default: undefined },
    averageGenderConfidence: { type: Number, default: undefined },
    averageAge: { type: Number, default: undefined },
    faces: { type: [cctvFaceEvidenceSchema], default: undefined },
  },
  { _id: false, minimize: false }
);

const cctvMlEvidenceSchema = new mongoose.Schema(
  {
    schemaVersion: { type: String, trim: true, default: "2026-07-06" },
    source: { type: String, trim: true, default: undefined },
    camera: { type: cctvCameraEvidenceSchema, default: () => ({}) },
    frame: { type: cctvFrameEvidenceSchema, default: () => ({}) },
    trigger: { type: cctvTriggerEvidenceSchema, default: () => ({}) },
    gesture: { type: cctvGestureEvidenceSchema, default: () => ({}) },
    voice: { type: cctvVoiceEvidenceSchema, default: () => ({}) },
    gender: { type: cctvGenderEvidenceSchema, default: () => ({}) },
    modelVersions: { type: mongoose.Schema.Types.Mixed, default: {} },
    rawGenderContext: { type: mongoose.Schema.Types.Mixed, default: null },
    rawPayload: { type: mongoose.Schema.Types.Mixed, default: null },
  },
  { _id: false, minimize: false }
);

const cctvSosAlertSchema = new mongoose.Schema(
  {
    location: {
      type: { type: String, default: "Point", enum: ["Point"] },
      coordinates: { type: [Number], required: true },
      accuracy: Number,
    },
    eventId: { type: String, trim: true, default: undefined },
    source: { type: String, trim: true, default: "CCTV" },
    ingestSource: { type: String, trim: true, default: undefined },
    cameraId: { type: String, trim: true, default: undefined },
    cameraName: { type: String, trim: true, default: undefined },
    cameraLocationLabel: { type: String, trim: true, default: undefined },
    frameTime: { type: String, trim: true, default: undefined },
    frameNumber: { type: Number, default: undefined },
    fps: { type: Number, default: undefined },
    triggerType: { type: String, trim: true, default: undefined },
    triggerLabel: { type: String, trim: true, default: undefined },
    triggerReason: { type: String, trim: true, default: undefined },
    triggerConfidence: { type: Number, default: undefined },
    handDetected: { type: Boolean, default: undefined },
    gestureLabel: { type: String, trim: true, default: undefined },
    gestureConfidence: { type: Number, default: undefined },
    voiceDetected: { type: Boolean, default: undefined },
    voiceEventId: { type: String, trim: true, default: undefined },
    voiceMatchedPhrase: { type: String, trim: true, default: undefined },
    voiceConfidence: { type: Number, default: undefined },
    genderEnabled: { type: Boolean, default: undefined },
    genderReady: { type: Boolean, default: undefined },
    genderDetected: { type: Boolean, default: undefined },
    genderEstimate: { type: Boolean, default: undefined },
    genderEngine: { type: String, trim: true, default: undefined },
    genderModelVersion: { type: String, trim: true, default: undefined },
    faceModelVersion: { type: String, trim: true, default: undefined },
    faceCount: { type: Number, default: undefined },
    maleCount: { type: Number, default: undefined },
    femaleCount: { type: Number, default: undefined },
    unknownGenderCount: { type: Number, default: undefined },
    modelVersions: { type: mongoose.Schema.Types.Mixed, default: {} },
    ml: { type: cctvMlEvidenceSchema, default: () => ({}) },
    status: { type: String, enum: ["active", "resolved"], default: "active" },
    sos_img: { type: String, required: true },
    resolvedAt: { type: Date, default: null },
    resolvedBy: { type: mongoose.Schema.Types.ObjectId, ref: "Admin", default: null },
  },
  { timestamps: true, minimize: false }
);

cctvSosAlertSchema.index({ location: "2dsphere" });
cctvSosAlertSchema.index({ status: 1, createdAt: -1 });
cctvSosAlertSchema.index({ eventId: 1 }, { unique: true, sparse: true });
cctvSosAlertSchema.index({ cameraId: 1, createdAt: -1 });

export const CCTVSOSAlert = mongoose.model("cctv_sos_alert", cctvSosAlertSchema);

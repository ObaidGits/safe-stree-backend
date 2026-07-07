import { body, param, validationResult } from "express-validator";
import { ApiError } from "../utils/ApiError.js";
import { removeCCTVImage } from "../utils/cctvAlertMetadata.js";

/**
 * Middleware to check validation results
 */
export const validate = async (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    if (req.savedFileName) {
      try {
        await removeCCTVImage(req.savedFileName);
      } catch (cleanupError) {
        console.warn("Failed to clean up invalid CCTV upload", {
          fileName: req.savedFileName,
          error: cleanupError?.message || cleanupError,
        });
      }
    }

    const messages = errors.array().map((e) => e.msg);
    throw new ApiError(400, messages.join(", "));
  }
  return next();
};

/**
 * User registration validation rules
 */
export const registerUserRules = [
  body("username")
    .trim()
    .notEmpty().withMessage("Username is required")
    .isLength({ min: 3, max: 30 }).withMessage("Username must be 3-30 characters")
    .matches(/^[a-zA-Z0-9_]+$/).withMessage("Username can only contain letters, numbers, and underscores"),
  
  body("email")
    .trim()
    .notEmpty().withMessage("Email is required")
    .isEmail().withMessage("Invalid email format")
    .normalizeEmail(),
  
  body("fullName")
    .trim()
    .notEmpty().withMessage("Full name is required")
    .isLength({ min: 2, max: 100 }).withMessage("Full name must be 2-100 characters"),
  
  body("contact")
    .trim()
    .notEmpty().withMessage("Contact number is required")
    .matches(/^\+?[0-9]{10,15}$/).withMessage("Invalid phone number (10-15 digits, optional + prefix)"),
  
  body("age")
    .notEmpty().withMessage("Age is required")
    .isInt({ min: 13, max: 120 }).withMessage("Age must be between 13 and 120"),
  
  body("password")
    .notEmpty().withMessage("Password is required")
    .isLength({ min: 6 }).withMessage("Password must be at least 6 characters")
    .matches(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/).withMessage("Password must contain uppercase, lowercase, and number"),
];

/**
 * User login validation rules
 * optional({ values: 'falsy' }) treats empty strings as "not provided"
 */
export const loginUserRules = [
  body("email")
    .optional({ values: "falsy" })
    .isEmail().withMessage("Invalid email format")
    .normalizeEmail(),
  body("username")
    .optional({ values: "falsy" })
    .trim(),
  body("password").notEmpty().withMessage("Password is required"),
];

/**
 * Admin registration validation rules
 */
export const registerAdminRules = [
  body("officerName")
    .trim()
    .notEmpty().withMessage("Officer name is required")
    .isLength({ min: 2, max: 100 }).withMessage("Officer name must be 2-100 characters"),
  
  body("email")
    .trim()
    .notEmpty().withMessage("Email is required")
    .isEmail().withMessage("Invalid email format")
    .normalizeEmail(),
  
  body("policeStation")
    .trim()
    .notEmpty().withMessage("Police station is required")
    .isLength({ min: 2, max: 200 }).withMessage("Police station must be 2-200 characters"),
  
  body("password")
    .notEmpty().withMessage("Password is required")
    .isLength({ min: 6 }).withMessage("Password must be at least 6 characters"),
];

/**
 * Admin login validation rules
 * Only email + password required (no police station)
 */
export const loginAdminRules = [
  body("email")
    .trim()
    .notEmpty().withMessage("Email is required")
    .isEmail().withMessage("Invalid email format")
    .normalizeEmail(),
  body("password").notEmpty().withMessage("Password is required"),
];

/**
 * SOS creation validation rules
 */
export const sosRules = [
  body("longitude")
    .notEmpty().withMessage("Longitude is required")
    .isFloat({ min: -180, max: 180 }).withMessage("Longitude must be between -180 and 180"),
  
  body("latitude")
    .notEmpty().withMessage("Latitude is required")
    .isFloat({ min: -90, max: 90 }).withMessage("Latitude must be between -90 and 90"),
  
  body("accuracy")
    .optional({ values: "falsy" })
    .isFloat({ min: 0 }).withMessage("Accuracy must be a positive number"),
];

const isJsonObjectValue = (value) => {
  if (value === undefined || value === null || value === "") {
    return true;
  }

  if (typeof value === "object" && !Array.isArray(value)) {
    return true;
  }

  if (typeof value !== "string") {
    return false;
  }

  try {
    const parsed = JSON.parse(value);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed);
  } catch {
    return false;
  }
};

const isJsonArrayValue = (value) => {
  if (value === undefined || value === null || value === "") {
    return true;
  }

  if (Array.isArray(value)) {
    return true;
  }

  if (typeof value !== "string") {
    return false;
  }

  try {
    return Array.isArray(JSON.parse(value));
  } catch {
    return false;
  }
};

const hasContent = (value) =>
  value !== undefined &&
  value !== null &&
  !(typeof value === "string" && value.trim() === "");

const parseMaybeJsonObject = (value) => {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }

  if (typeof value === "object") {
    return value;
  }

  if (typeof value !== "string") {
    return undefined;
  }

  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
};

const hasCctvLocation = (req) => {
  const hasFlatLocation = hasContent(req.body?.longitude) && hasContent(req.body?.latitude);
  if (hasFlatLocation) {
    return true;
  }

  const mlPayload = parseMaybeJsonObject(req.body?.ml);
  const mlLocation = mlPayload && typeof mlPayload === "object" ? mlPayload.location : undefined;
  if (!mlLocation || typeof mlLocation !== "object") {
    return false;
  }

  const coordinates = Array.isArray(mlLocation.coordinates) ? mlLocation.coordinates : [];
  const hasNestedCoordinates =
    hasContent(coordinates[0]) && hasContent(coordinates[1]);
  const hasNestedLatLng =
    hasContent(mlLocation.longitude) &&
    hasContent(mlLocation.latitude);

  return hasNestedCoordinates || hasNestedLatLng;
};

/**
 * CCTV SOS metadata validation rules
 * Accepts the richer ML payload while remaining backward-compatible with old alerts.
 */
export const cctvSosRules = [
  body()
    .custom((_, { req }) => {
      if (hasCctvLocation(req)) {
        return true;
      }
      throw new Error("Either flat coordinates or ml.location must be provided");
    }),

  body("longitude")
    .optional({ values: "falsy" })
    .isFloat({ min: -180, max: 180 }).withMessage("Longitude must be between -180 and 180"),

  body("latitude")
    .optional({ values: "falsy" })
    .isFloat({ min: -90, max: 90 }).withMessage("Latitude must be between -90 and 90"),

  body("accuracy")
    .optional({ values: "falsy" })
    .isFloat({ min: 0 }).withMessage("Accuracy must be a positive number"),

  body("eventId")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ min: 8, max: 200 })
    .withMessage("eventId must be 8-200 characters"),

  body("source")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ min: 2, max: 64 })
    .withMessage("source must be 2-64 characters"),

  body("ingestSource")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ min: 2, max: 64 })
    .withMessage("ingestSource must be 2-64 characters"),

  body("cameraId")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("cameraId must be at most 128 characters"),

  body("cameraName")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("cameraName must be at most 128 characters"),

  body("cameraLocationLabel")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 160 })
    .withMessage("cameraLocationLabel must be at most 160 characters"),

  body("frameTime")
    .optional({ values: "falsy" })
    .isISO8601()
    .withMessage("frameTime must be a valid ISO timestamp"),

  body("frameNumber")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("frameNumber must be a positive integer"),

  body("fps")
    .optional({ values: "falsy" })
    .isFloat({ min: 0 })
    .withMessage("fps must be a positive number"),

  body("triggerType")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("triggerType must be at most 64 characters"),

  body("triggerLabel")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("triggerLabel must be at most 128 characters"),

  body("triggerReason")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 256 })
    .withMessage("triggerReason must be at most 256 characters"),

  body("triggerConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("triggerConfidence must be between 0 and 1"),

  body("handDetected")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("handDetected must be boolean"),

  body("gestureLabel")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("gestureLabel must be at most 64 characters"),

  body("gestureRawConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("gestureRawConfidence must be between 0 and 1"),

  body("gestureConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("gestureConfidence must be between 0 and 1"),

  body("gestureQualityScore")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("gestureQualityScore must be between 0 and 1"),

  body("gestureWindowCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("gestureWindowCount must be a positive integer"),

  body("gesturePositiveCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("gesturePositiveCount must be a positive integer"),

  body("gestureModelId")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("gestureModelId must be at most 128 characters"),

  body("gestureModelDir")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 256 })
    .withMessage("gestureModelDir must be at most 256 characters"),

  body("gestureEngine")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("gestureEngine must be at most 64 characters"),

  body("gestureClassifier")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("gestureClassifier must be at most 64 characters"),

  body("voiceDetected")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("voiceDetected must be boolean"),

  body("voiceEventId")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 200 })
    .withMessage("voiceEventId must be at most 200 characters"),

  body("voiceTranscript")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 400 })
    .withMessage("voiceTranscript must be at most 400 characters"),

  body("voiceMatchedPhrase")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 200 })
    .withMessage("voiceMatchedPhrase must be at most 200 characters"),

  body("voiceMatchKind")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("voiceMatchKind must be at most 64 characters"),

  body("voiceSource")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("voiceSource must be at most 64 characters"),

  body("voiceModelVersion")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("voiceModelVersion must be at most 128 characters"),

  body("voiceEngine")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("voiceEngine must be at most 64 characters"),

  body("voiceConfidenceRaw")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("voiceConfidenceRaw must be between 0 and 1"),

  body("voiceConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("voiceConfidence must be between 0 and 1"),

  body("voiceRecognitionConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("voiceRecognitionConfidence must be between 0 and 1"),

  body("genderEnabled")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("genderEnabled must be boolean"),

  body("genderReady")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("genderReady must be boolean"),

  body("genderUpdated")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("genderUpdated must be boolean"),

  body("genderDetected")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("genderDetected must be boolean"),

  body("genderEstimate")
    .optional({ values: "falsy" })
    .isBoolean()
    .withMessage("genderEstimate must be boolean"),

  body("genderEngine")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("genderEngine must be at most 64 characters"),

  body("genderModelVersion")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("genderModelVersion must be at most 128 characters"),

  body("faceModelVersion")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 128 })
    .withMessage("faceModelVersion must be at most 128 characters"),

  body("genderFrameSize")
    .optional({ values: "falsy" })
    .custom(isJsonArrayValue)
    .withMessage("genderFrameSize must be a JSON array"),

  body("genderSkippedReason")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 256 })
    .withMessage("genderSkippedReason must be at most 256 characters"),

  body("genderEstimateLabel")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("genderEstimateLabel must be at most 64 characters"),

  body("genderSource")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 64 })
    .withMessage("genderSource must be at most 64 characters"),

  body("faceCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("faceCount must be a positive integer"),

  body("maleCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("maleCount must be a positive integer"),

  body("femaleCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("femaleCount must be a positive integer"),

  body("unknownGenderCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("unknownGenderCount must be a positive integer"),

  body("rawFaceCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("rawFaceCount must be a positive integer"),

  body("rawMaleCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("rawMaleCount must be a positive integer"),

  body("rawFemaleCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("rawFemaleCount must be a positive integer"),

  body("rawUnknownGenderCount")
    .optional({ values: "falsy" })
    .isInt({ min: 0 })
    .withMessage("rawUnknownGenderCount must be a positive integer"),

  body("genderAverageFaceConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("genderAverageFaceConfidence must be between 0 and 1"),

  body("genderAverageConfidence")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 1 })
    .withMessage("genderAverageConfidence must be between 0 and 1"),

  body("genderAverageAge")
    .optional({ values: "falsy" })
    .isFloat({ min: 0, max: 120 })
    .withMessage("genderAverageAge must be between 0 and 120"),

  body("genderFaces")
    .optional({ values: "falsy" })
    .custom(isJsonArrayValue)
    .withMessage("genderFaces must be a JSON array"),

  body("modelVersions")
    .optional({ values: "falsy" })
    .custom(isJsonObjectValue)
    .withMessage("modelVersions must be a JSON object"),

  body("genderContext")
    .optional({ values: "falsy" })
    .custom(isJsonObjectValue)
    .withMessage("genderContext must be a JSON object"),

  body("ml")
    .optional({ values: "falsy" })
    .custom(isJsonObjectValue)
    .withMessage("ml must be a JSON object"),
];

/**
 * MongoDB ObjectId validation
 */
export const objectIdRule = (paramName = "id") => [
  param(paramName).isMongoId().withMessage(`Invalid ${paramName} format`),
];

/**
 * Password change validation rules
 */
export const changePasswordRules = [
  body("oldPassword").notEmpty().withMessage("Old password is required"),
  body("newPassword")
    .notEmpty().withMessage("New password is required")
    .isLength({ min: 6 }).withMessage("New password must be at least 6 characters")
    .matches(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/).withMessage("Password must contain uppercase, lowercase, and number"),
];

/**
 * Admin management: update user rules
 */
export const updateManagedUserRules = [
  body("fullName")
    .optional()
    .trim()
    .isLength({ min: 2, max: 100 }).withMessage("Full name must be 2-100 characters"),

  body("username")
    .optional()
    .trim()
    .isLength({ min: 3, max: 30 }).withMessage("Username must be 3-30 characters")
    .matches(/^[a-zA-Z0-9_]+$/).withMessage("Username can only contain letters, numbers, and underscores"),

  body("email")
    .optional()
    .trim()
    .isEmail().withMessage("Invalid email format")
    .normalizeEmail(),

  body("contact")
    .optional()
    .trim()
    .matches(/^\+?[0-9]{10,15}$/).withMessage("Invalid phone number (10-15 digits, optional + prefix)"),

  body("age")
    .optional()
    .isInt({ min: 13, max: 120 }).withMessage("Age must be between 13 and 120")
    .toInt(),

  body("bloodGroup")
    .optional()
    .isIn(["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
    .withMessage("Invalid blood group"),

  body("medicalInfo")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 1500 }).withMessage("Medical info must be at most 1500 characters"),

  body("medicalConditions")
    .optional()
    .custom((value) => {
      if (typeof value === "string") {
        return value
          .split(",")
          .map((item) => item.trim())
          .every((item) => item.length <= 100);
      }

      if (Array.isArray(value)) {
        return value.every(
          (item) => typeof item === "string" && item.trim().length <= 100
        );
      }

      return false;
    })
    .withMessage("medicalConditions must be a string or array with max 100 chars per item"),

  body("allergies")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 500 }).withMessage("Allergies must be at most 500 characters"),

  body("city")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 100 }).withMessage("City must be at most 100 characters"),

  body("state")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 100 }).withMessage("State must be at most 100 characters"),

  body("address")
    .optional({ values: "falsy" })
    .trim()
    .isLength({ max: 300 }).withMessage("Address must be at most 300 characters"),

  body("pincode")
    .optional({ values: "falsy" })
    .trim()
    .matches(/^[0-9]{4,10}$/).withMessage("Pincode must be 4-10 digits"),

  body("emergencyContact1")
    .optional({ values: "falsy" })
    .trim()
    .matches(/^\+?[0-9]{10,15}$/).withMessage("Invalid emergency contact 1"),

  body("emergencyContact2")
    .optional({ values: "falsy" })
    .trim()
    .matches(/^\+?[0-9]{10,15}$/).withMessage("Invalid emergency contact 2"),

  body("emergencyEmail")
    .optional({ values: "falsy" })
    .trim()
    .isEmail().withMessage("Invalid emergency email format")
    .normalizeEmail(),

  body("shareMedicalInfo")
    .optional()
    .isBoolean().withMessage("shareMedicalInfo must be boolean")
    .toBoolean(),

  body("shareLocation")
    .optional()
    .isBoolean().withMessage("shareLocation must be boolean")
    .toBoolean(),

  body("password")
    .optional({ values: "falsy" })
    .isLength({ min: 6 }).withMessage("Password must be at least 6 characters")
    .matches(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/).withMessage("Password must contain uppercase, lowercase, and number"),

  body("isActive")
    .optional()
    .isBoolean().withMessage("isActive must be boolean")
    .toBoolean(),
];

/**
 * Admin management: update admin rules
 */
export const updateManagedAdminRules = [
  body("officerName")
    .optional()
    .trim()
    .isLength({ min: 2, max: 100 }).withMessage("Officer name must be 2-100 characters"),

  body("email")
    .optional()
    .trim()
    .isEmail().withMessage("Invalid email format")
    .normalizeEmail(),

  body("policeStation")
    .optional()
    .trim()
    .isLength({ min: 2, max: 200 }).withMessage("Police station must be 2-200 characters"),

  body("password")
    .optional()
    .isLength({ min: 6 }).withMessage("Password must be at least 6 characters"),

  body("isActive")
    .optional()
    .isBoolean().withMessage("isActive must be boolean")
    .toBoolean(),
];

/**
 * Admin management: toggle status rules
 */
export const toggleStatusRules = [
  body("isActive")
    .exists().withMessage("isActive is required")
    .isBoolean().withMessage("isActive must be boolean")
    .toBoolean(),
];

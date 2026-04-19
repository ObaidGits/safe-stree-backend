import { body, param, validationResult } from "express-validator";
import { ApiError } from "../utils/ApiError.js";

/**
 * Middleware to check validation results
 */
export const validate = (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    const messages = errors.array().map((e) => e.msg);
    throw new ApiError(400, messages.join(", "));
  }
  next();
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
    .optional()
    .isFloat({ min: 0 }).withMessage("Accuracy must be a positive number"),
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

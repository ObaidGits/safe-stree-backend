import { Router } from "express";
import {
  changeCurrentPassword,
  getCurrentUser,
  loginUser,
  logoutUser,
  refreshAccessToken,
  registerUser,
  updateProfile
} from "../controllers/user.controller.js";

import { verifyJWT } from "../middlewares/auth.middleware.js";
import { userMulter } from "../middlewares/user.middleware.js";
import { authLimiter } from "../middlewares/rateLimit.middleware.js";
import {
  registerUserRules,
  loginUserRules,
  changePasswordRules,
  validate
} from "../middlewares/validation.middleware.js";

const router = Router();

/**
 * Register User
 * PUBLIC (rate limited)
 * avatar upload required
 */
router.post(
  "/register",
  authLimiter,
  userMulter.single("avatar"),
  registerUserRules,
  validate,
  registerUser
);

/**
 * Login
 * PUBLIC (rate limited)
 */
router.post("/login", authLimiter, loginUserRules, validate, loginUser);

/**
 * Logout
 * PROTECTED
 */
router.post("/logout", verifyJWT, logoutUser);

/**
 * Refresh Token
 * PUBLIC (validated internally)
 */
router.post("/refresh-token", refreshAccessToken);

/**
 * Change Password
 * PROTECTED
 */
router.post("/change-password", verifyJWT, changePasswordRules, validate, changeCurrentPassword);

/**
 * Get Current User
 * PROTECTED
 * POST kept intentionally for compatibility
 */
router.post("/current-user", verifyJWT, getCurrentUser);

/**
 * Update Profile
 * PROTECTED
 * avatar upload optional
 */
router.put("/update-profile", verifyJWT, userMulter.single("avatar"), updateProfile);

export default router;

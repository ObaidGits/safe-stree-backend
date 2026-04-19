import { Router } from "express";
import {
  getCurrentAdmin,
  loginAdmin,
  logoutAdmin,
  registerAdmin
} from "../controllers/admin.controller.js";
import {
  createManagedAdmin,
  getManagedAdmins,
  getManagedUsers,
  getManagementOverview,
  toggleManagedAdminStatus,
  toggleManagedUserStatus,
  updateManagedAdmin,
  updateManagedUser,
} from "../controllers/admin.management.controller.js";
import { requireAdmin, verifyJWT } from "../middlewares/auth.middleware.js";
import { authLimiter } from "../middlewares/rateLimit.middleware.js";
import { userMulter } from "../middlewares/user.middleware.js";
import {
  loginAdminRules,
  objectIdRule,
  registerAdminRules,
  toggleStatusRules,
  updateManagedAdminRules,
  updateManagedUserRules,
  validate
} from "../middlewares/validation.middleware.js";

const router = Router();

/**
 * Register Admin
 * PUBLIC (rate limited)
 */
router.post("/register", authLimiter, registerAdminRules, validate, registerAdmin);

/**
 * Login Admin
 * PUBLIC (rate limited)
 */
router.post("/login", authLimiter, loginAdminRules, validate, loginAdmin);

/**
 * Logout Admin
 * PROTECTED
 */
router.post("/logout", verifyJWT, logoutAdmin);

/**
 * Get Current Admin
 * PROTECTED
 * Note: POST kept intentionally (frontend compatibility)
 */
router.post("/current-admin", verifyJWT, getCurrentAdmin);

/**
 * Management Overview
 * PROTECTED (Admin only)
 */
router.get("/management/overview", verifyJWT, requireAdmin, getManagementOverview);

/**
 * User Management
 * PROTECTED (Admin only)
 */
router.get("/management/users", verifyJWT, requireAdmin, getManagedUsers);
router.patch(
  "/management/users/:userId",
  verifyJWT,
  requireAdmin,
  objectIdRule("userId"),
  userMulter.single("avatar"),
  updateManagedUserRules,
  validate,
  updateManagedUser
);
router.patch(
  "/management/users/:userId/status",
  verifyJWT,
  requireAdmin,
  objectIdRule("userId"),
  toggleStatusRules,
  validate,
  toggleManagedUserStatus
);

/**
 * Admin Management
 * PROTECTED (Admin only)
 */
router.get("/management/admins", verifyJWT, requireAdmin, getManagedAdmins);
router.post("/management/admins", verifyJWT, requireAdmin, registerAdminRules, validate, createManagedAdmin);
router.patch(
  "/management/admins/:adminId",
  verifyJWT,
  requireAdmin,
  objectIdRule("adminId"),
  updateManagedAdminRules,
  validate,
  updateManagedAdmin
);
router.patch(
  "/management/admins/:adminId/status",
  verifyJWT,
  requireAdmin,
  objectIdRule("adminId"),
  toggleStatusRules,
  validate,
  toggleManagedAdminStatus
);

export default router;

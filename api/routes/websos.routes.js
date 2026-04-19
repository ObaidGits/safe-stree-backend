import express from "express";
import {
  createSOS,
  getActiveAlerts,
  getAllAlerts,
  markAlertResolved
} from "../controllers/websos.controller.js";
import { requireAdmin, verifyJWT } from "../middlewares/auth.middleware.js";
import { sosLimiter } from "../middlewares/rateLimit.middleware.js";
import { sosRules, objectIdRule, validate } from "../middlewares/validation.middleware.js";

const router = express.Router();

/**
 * Create Web SOS Alert
 * Protected by JWT + Rate limited
 */
router.post("/", verifyJWT, sosLimiter, sosRules, validate, createSOS);

/**
 * Get Active Alerts
 * Protected by JWT
 */
router.get("/active", verifyJWT, requireAdmin, getActiveAlerts);

/**
 * Mark Alert Resolved
 * Protected by JWT
 */
router.put("/set-sos-resolved/:id", verifyJWT, requireAdmin, objectIdRule("id"), validate, markAlertResolved);

/**
 * Get All Alerts
 * Protected by JWT
 */
router.get("/all-alerts", verifyJWT, requireAdmin, getAllAlerts);

export default router;

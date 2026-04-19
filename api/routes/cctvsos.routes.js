import express from "express";
import {
  createCCTVSOS,
  getActiveCCTVAlerts,
  getAllCCTVAlerts,
  markCCTVAlertResolved
} from "../controllers/cctvsos.controller.js";
import { uploadCCTVSOS } from "../middlewares/cctvsos.multer.js";
import { verifyApiKey } from "../middlewares/apiKey.middleware.js";
import { verifyInternalService } from "../middlewares/internalService.middleware.js";
import { requireAdmin, verifyJWT } from "../middlewares/auth.middleware.js";
import { sosLimiter } from "../middlewares/rateLimit.middleware.js";
import { sosRules, objectIdRule, validate } from "../middlewares/validation.middleware.js";

const router = express.Router();

/**
 * Create CCTV SOS Alert
 * Protected by API Key (for ML backend)
 * Rate limited to prevent spam
 */
router.post(
  "/",
  verifyApiKey,
  sosLimiter,
  uploadCCTVSOS.single("sos_img"),
  sosRules,
  validate,
  createCCTVSOS
);

/**
 * Create CCTV SOS Alert (Internal ML service route)
 * Protected by internal service token
 */
router.post(
  "/internal",
  verifyInternalService,
  sosLimiter,
  uploadCCTVSOS.single("sos_img"),
  sosRules,
  validate,
  createCCTVSOS
);

/**
 * Get Active CCTV Alerts
 * Protected by JWT (admin only)
 */
router.get("/active", verifyJWT, requireAdmin, getActiveCCTVAlerts);

/**
 * Get All CCTV Alerts
 * Protected by JWT (admin only)
 */
router.get("/all-alerts", verifyJWT, requireAdmin, getAllCCTVAlerts);

/**
 * Mark CCTV Alert Resolved
 * Protected by JWT (admin only)
 */
router.put("/set-sos-resolved/:id", verifyJWT, requireAdmin, objectIdRule("id"), validate, markCCTVAlertResolved);

export default router;

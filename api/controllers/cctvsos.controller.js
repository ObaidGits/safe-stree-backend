import { broadcastNewAlert } from "../socket/index.js";
import { CCTVSOSAlert } from "../models/cctvsos.model.js";
import { ApiError } from "../utils/ApiError.js";
import { ApiResponse } from "../utils/ApiResponse.js";
import { asyncHandler } from "../utils/asyncHandler.js";
import { logSOSAlert, logSecurityEvent } from "../utils/logger.js";
import {
  buildCCTVAlertDocument,
  buildCCTVAlertLogContext,
  removeCCTVImage,
} from "../utils/cctvAlertMetadata.js";

/**
 * Create CCTV SOS Alert
 * POST /api/v1/cctv
 * Protected by API Key (for ML backend)
 */
export const createCCTVSOS = asyncHandler(async (req, res) => {
  const sos_img = req.savedFileName;

  if (!sos_img) {
    throw new ApiError(400, "SOS image not received");
  }

  const ingestSource = req.internalService?.name || req.body?.source || "backend_ml";
  const alertDocument = buildCCTVAlertDocument({
    body: req.body,
    savedFileName: sos_img,
    ingestSource,
  });

  const [longitude, latitude] = alertDocument?.location?.coordinates || [];
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
    await removeCCTVImage(sos_img);
    throw new ApiError(400, "Invalid CCTV alert location");
  }

  if (alertDocument.eventId) {
    const existingAlert = await CCTVSOSAlert.findOne({ eventId: alertDocument.eventId });
    if (existingAlert) {
      await removeCCTVImage(sos_img);
      logSecurityEvent("SOS_ALERT_DUPLICATE", {
        alertType: "CCTV",
        alertId: existingAlert._id,
        eventId: alertDocument.eventId,
        ingestSource,
        triggerType: existingAlert.triggerType || alertDocument.triggerType || null,
        cameraId: existingAlert.cameraId || alertDocument.cameraId || null,
        timestamp: new Date().toISOString(),
      });

      return res.status(200).json(
        new ApiResponse(
          200,
          {
            alertId: existingAlert._id,
            duplicate: true,
            eventId: alertDocument.eventId,
          },
          "CCTV SOS alert already recorded"
        )
      );
    }
  }

  let alert;

  try {
    alert = await CCTVSOSAlert.create(alertDocument);
  } catch (error) {
    if (error?.code === 11000 && alertDocument.eventId) {
      await removeCCTVImage(sos_img);

      const existingAlert = await CCTVSOSAlert.findOne({ eventId: alertDocument.eventId });
      if (existingAlert) {
        logSecurityEvent("SOS_ALERT_DUPLICATE", {
          alertType: "CCTV",
          alertId: existingAlert._id,
          eventId: alertDocument.eventId,
          ingestSource,
          triggerType: existingAlert.triggerType || alertDocument.triggerType || null,
          cameraId: existingAlert.cameraId || alertDocument.cameraId || null,
          timestamp: new Date().toISOString(),
        });

        return res.status(200).json(
          new ApiResponse(
            200,
            {
              alertId: existingAlert._id,
              duplicate: true,
              eventId: alertDocument.eventId,
            },
            "CCTV SOS alert already recorded"
          )
        );
      }
    }

    await removeCCTVImage(sos_img);
    throw error;
  }

  if (!alert) {
    throw new ApiError(500, "Failed to save CCTV SOS alert");
  }

  // Log for audit trail with the sanitized evidence summary
  logSOSAlert("CCTV", alert._id, buildCCTVAlertLogContext(alert), req.internalService?.name || null);

  broadcastNewAlert({
    ...alert.toObject(),
    userId: null,
  });

  return res
    .status(201)
    .json(
      new ApiResponse(
        201,
        {
          alertId: alert._id,
          eventId: alert.eventId || null,
        },
        "CCTV SOS submitted successfully"
      )
    );
});

/**
 * Get Active CCTV Alerts with Pagination
 * GET /api/v1/cctv/active
 */
export const getActiveCCTVAlerts = asyncHandler(async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page, 10) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit, 10) || 50));
  const skip = (page - 1) * limit;

  const [alerts, total] = await Promise.all([
    CCTVSOSAlert.find({ status: "active" })
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    CCTVSOSAlert.countDocuments({ status: "active" }),
  ]);

  return res.status(200).json(
    new ApiResponse(200, {
      alerts,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit),
      },
    })
  );
});

/**
 * Get All CCTV Alerts with Pagination
 * GET /api/v1/cctv/all-alerts
 */
export const getAllCCTVAlerts = asyncHandler(async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page, 10) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit, 10) || 50));
  const skip = (page - 1) * limit;
  const status = req.query.status; // Optional filter

  const filter = status ? { status } : {};

  const [alerts, total] = await Promise.all([
    CCTVSOSAlert.find(filter)
      .populate("resolvedBy", "officerName policeStation")
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    CCTVSOSAlert.countDocuments(filter),
  ]);

  return res.status(200).json(
    new ApiResponse(200, {
      alerts,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit),
      },
    })
  );
});

/**
 * Mark CCTV Alert as Resolved
 * PUT /api/v1/cctv/set-sos-resolved/:id
 */
export const markCCTVAlertResolved = asyncHandler(async (req, res) => {
  const { id } = req.params;
  const resolvedBy = req.admin?._id;

  if (!resolvedBy) {
    throw new ApiError(403, "Admin access required");
  }

  const updated = await CCTVSOSAlert.findByIdAndUpdate(
    id,
    {
      status: "resolved",
      resolvedAt: new Date(),
      resolvedBy,
    },
    { new: true }
  );

  if (!updated) {
    throw new ApiError(404, "SOS alert not found");
  }

  return res
    .status(200)
    .json(new ApiResponse(200, updated, "CCTV SOS alert marked as resolved"));
});

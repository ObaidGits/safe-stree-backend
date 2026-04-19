import { broadcastNewAlert } from "../socket/index.js";
import { SOSAlert } from "../models/websos.model.js";
import { ApiError } from "../utils/ApiError.js";
import { ApiResponse } from "../utils/ApiResponse.js";
import { asyncHandler } from "../utils/asyncHandler.js";
import { logSOSAlert } from "../utils/logger.js";
import mongoose from "mongoose";
import https from "https";

/**
 * Geocode coordinates to address using OpenCage API
 * Uses native https module for better Node.js compatibility
 */
const geocodeCoordinates = (lat, lng) => {
  return new Promise((resolve) => {
    try {
      const apiKey = process.env.OPENCAGE_API_KEY;
      
      if (!apiKey) {
        console.error('❌ OPENCAGE_API_KEY not found in environment variables');
        resolve('Address unavailable (API key missing)');
        return;
      }
      
      const url = `https://api.opencagedata.com/geocode/v1/json?q=${lat}+${lng}&key=${apiKey}`;
      console.log(`🌍 Geocoding: ${lat}, ${lng}`);
      
      const geocodeRequest = https.get(url, (res) => {
        let data = '';
        
        res.on('data', (chunk) => {
          data += chunk;
        });
        
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            
            // Handle API errors
            if (parsed.status && parsed.status.code !== 200) {
              const code = parsed.status.code;
              const message = parsed.status.message || 'Unknown error';
              
              if (code === 401) {
                console.error('❌ OpenCage: Invalid API key - Token expired or invalid');
                resolve('Address unavailable (Token expired)');
              } else if (code === 402) {
                console.error('❌ OpenCage: Quota exceeded - Payment required');
                resolve('Address unavailable (Quota exceeded)');
              } else if (code === 403) {
                console.error('❌ OpenCage: Forbidden - IP blocked or suspended');
                resolve('Address unavailable (Access denied)');
              } else if (code === 429) {
                console.error('❌ OpenCage: Rate limit exceeded');
                resolve('Address unavailable (Rate limited)');
              } else {
                console.error(`❌ OpenCage error ${code}: ${message}`);
                resolve(`Address unavailable (Error: ${message})`);
              }
              return;
            }
            
            // Successfully got results
            if (parsed.results && parsed.results.length > 0) {
              const result = parsed.results[0];
              let formatted = result.formatted || '';
              
              // Remove "Unnamed Road," prefix if present
              if (formatted.toLowerCase().startsWith('unnamed road,')) {
                formatted = formatted.split(',').slice(1).map(p => p.trim()).join(', ');
              }
              
              console.log(`✅ Geocoded: ${formatted}`);
              resolve(formatted);
            } else {
              console.warn('⚠️ OpenCage: No results found for coordinates');
              resolve('Address not found');
            }
          } catch (parseError) {
            console.error('❌ Geocoding parse error:', parseError.message);
            resolve('Address unavailable (Parse error)');
          }
        });
        
      });

      geocodeRequest.setTimeout(5000, () => {
        geocodeRequest.destroy(new Error('Geocoding request timeout'));
      });

      geocodeRequest.on('error', (error) => {
        console.error('❌ Geocoding request error:', error.message);
        resolve('Address unavailable (Network error)');
      });
      
    } catch (error) {
      console.error('❌ Geocoding error:', error.message);
      resolve('Address unavailable');
    }
  });
};

/**
 * Create Web SOS Alert
 * POST /api/v1/sos
 */
export const createSOS = asyncHandler(async (req, res) => {
  const userId = req.user?._id;
  const { longitude, latitude, accuracy } = req.body;

  // Geocode coordinates to get live address
  const liveAddress = await geocodeCoordinates(parseFloat(latitude), parseFloat(longitude));

  const alert = await SOSAlert.create({
    userId,
    location: {
      type: "Point",
      coordinates: [parseFloat(longitude), parseFloat(latitude)],
      accuracy: accuracy ? parseFloat(accuracy) : undefined,
    },
    liveAddress,
  });

  if (!alert) {
    throw new ApiError(500, "Failed to save SOS alert");
  }

  // Log for audit trail
  logSOSAlert("WEB", alert._id, { longitude, latitude, accuracy }, userId);

  // Broadcast to admins (use main email instead of emergencyEmail)
  broadcastNewAlert({
    ...alert.toObject(),
    userId: {
      _id: req.user._id,
      email: req.user.email,
      contact: req.user.contact,
      avatar: req.user.avatar,
      fullName: req.user.fullName,
      age: req.user.age,
      bloodGroup: req.user.bloodGroup,
      medicalInfo: req.user.medicalInfo,
      medicalConditions: req.user.medicalConditions,
      allergies: req.user.allergies,
      emergencyContact1: req.user.emergencyContact1,
      emergencyContact2: req.user.emergencyContact2,
      address: req.user.address,
      city: req.user.city,
      state: req.user.state,
      pincode: req.user.pincode,
    },
    liveAddress,
    source: "Web",
  });

  return res
    .status(201)
    .json(new ApiResponse(201, { alertId: alert._id }, "Web SOS alert submitted successfully"));
});

/**
 * Get Active Alerts with Pagination
 * GET /api/v1/sos/active
 */
export const getActiveAlerts = asyncHandler(async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page, 10) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit, 10) || 50));
  const skip = (page - 1) * limit;

  const [alerts, total] = await Promise.all([
    SOSAlert.find({ status: "active" })
      .populate("userId", "fullName email contact avatar age bloodGroup medicalInfo medicalConditions allergies emergencyContact1 emergencyContact2 address city state pincode")
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    SOSAlert.countDocuments({ status: "active" }),
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
 * Get All Alerts with Pagination
 * GET /api/v1/sos/all-alerts
 */
export const getAllAlerts = asyncHandler(async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page, 10) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit, 10) || 50));
  const skip = (page - 1) * limit;
  const status = req.query.status; // Optional filter

  const filter = status ? { status } : {};

  const [alerts, total] = await Promise.all([
    SOSAlert.find(filter)
      .populate("userId", "fullName email contact avatar age bloodGroup medicalInfo medicalConditions allergies emergencyContact1 emergencyContact2 address city state pincode")
      .populate("resolvedBy", "officerName policeStation")
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    SOSAlert.countDocuments(filter),
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
 * Mark Alert as Resolved
 * PUT /api/v1/sos/set-sos-resolved/:id
 */
export const markAlertResolved = asyncHandler(async (req, res) => {
  const { id } = req.params;
  const resolvedBy = req.admin?._id;

  if (!resolvedBy) {
    throw new ApiError(403, "Admin access required");
  }

  const updated = await SOSAlert.findByIdAndUpdate(
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

  return res.status(200).json(
    new ApiResponse(200, updated, "Web SOS alert marked as resolved")
  );
});

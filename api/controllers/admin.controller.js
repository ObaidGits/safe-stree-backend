import { Admin } from "../models/admin.model.js";
import { ApiError } from "../utils/ApiError.js";
import { ApiResponse } from "../utils/ApiResponse.js";
import { asyncHandler } from "../utils/asyncHandler.js";
import { generateAccessAndRefreshToken } from "../utils/tokenGenerator.js";
import { cookieOptions, refreshCookieOptions } from "../config/cookie.config.js";
import { logSuccessfulLogin, logFailedLogin, logSecurityEvent } from "../utils/logger.js";

/**
 * Register new admin
 * POST /api/v1/admin/register
 */
export const registerAdmin = asyncHandler(async (req, res) => {
  const { officerName, email, policeStation, password, officersInStation = [] } = req.body;

  const existing = await Admin.findOne({ $or: [{ email: email.toLowerCase() }, { policeStation }] });
  if (existing) {
    throw new ApiError(409, "Admin with this email or police station already exists");
  }

  const newAdmin = await Admin.create({
    officerName,
    email: email.toLowerCase(),
    policeStation,
    password,
    officersInStation,
  });

  const sanitized = await Admin.findById(newAdmin._id).select("-password -refreshToken");

  logSecurityEvent("ADMIN_REGISTERED", {
    adminId: newAdmin._id,
    email: newAdmin.email,
    policeStation: newAdmin.policeStation,
    ip: req.ip,
  });

  return res.status(201).json(
    new ApiResponse(201, sanitized, "Admin registered successfully")
  );
});

/**
 * Login admin
 * POST /api/v1/admin/login
 * Only email + password required
 */
export const loginAdmin = asyncHandler(async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    throw new ApiError(400, "Email and password are required");
  }

  const admin = await Admin.findOne({ email: email.toLowerCase() });

  if (!admin) {
    logFailedLogin(email, req.ip, "Admin not found");
    throw new ApiError(404, "Admin not found");
  }

  if (!admin.isActive) {
    logFailedLogin(email, req.ip, "Admin account is disabled");
    throw new ApiError(403, "Admin account is disabled");
  }

  const isPasswordValid = await admin.isPasswordCorrect(password);
  if (!isPasswordValid) {
    logFailedLogin(email, req.ip, "Invalid credentials");
    throw new ApiError(401, "Invalid credentials");
  }

  const { accessToken, refreshToken } = await generateAccessAndRefreshToken(Admin, admin._id);
  const sanitized = await Admin.findById(admin._id).select("-password -refreshToken");

  logSuccessfulLogin(admin._id, admin.email, req.ip);

  return res
    .status(200)
    .cookie("accessToken", accessToken, cookieOptions)
    .cookie("refreshToken", refreshToken, refreshCookieOptions)
    .json(
      new ApiResponse(200, { admin: sanitized, accessToken, refreshToken }, "Admin logged in successfully")
    );
});

/**
 * Logout admin
 * POST /api/v1/admin/logout
 */
export const logoutAdmin = asyncHandler(async (req, res) => {
  // Support both req.admin and req.user for flexibility
  const adminId = req.admin?._id || req.user?._id;
  
  if (!adminId) {
    throw new ApiError(401, "Not authenticated");
  }

  await Admin.findByIdAndUpdate(adminId, { $unset: { refreshToken: 1 } });

  logSecurityEvent("ADMIN_LOGOUT", {
    adminId,
    ip: req.ip,
  });

  return res
    .status(200)
    .clearCookie("accessToken", cookieOptions)
    .clearCookie("refreshToken", refreshCookieOptions)
    .json(new ApiResponse(200, {}, "Admin logged out successfully"));
});

/**
 * Get current admin
 * POST /api/v1/admin/current-admin
 */
export const getCurrentAdmin = asyncHandler(async (req, res) => {
  if (!req.admin) {
    throw new ApiError(401, "Unauthorized - Admin access required");
  }

  return res.status(200).json(
    new ApiResponse(200, req.admin, "Current admin fetched successfully")
  );
});

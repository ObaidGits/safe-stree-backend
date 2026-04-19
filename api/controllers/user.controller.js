import { ApiResponse } from "../utils/ApiResponse.js";
import { ApiError } from "../utils/ApiError.js";
import { User } from "../models/user.model.js";
import { asyncHandler } from "../utils/asyncHandler.js";
import { generateAccessAndRefreshToken } from "../utils/tokenGenerator.js";
import { cookieOptions, refreshCookieOptions } from "../config/cookie.config.js";
import { logSuccessfulLogin, logFailedLogin, logSecurityEvent } from "../utils/logger.js";
import jwt from "jsonwebtoken";
import path from "path";
import fs from "fs";

const removeUploadedFile = async (filePath) => {
  if (!filePath || !fs.existsSync(filePath)) return;

  try {
    await fs.promises.unlink(filePath);
  } catch (error) {
    console.error("Failed to cleanup uploaded file:", error.message);
  }
};

/**
 * Register new user
 * POST /api/v1/users/register
 */
export const registerUser = asyncHandler(async (req, res) => {
  const { username, email, fullName, contact, age, password } = req.body;

  // Check for existing user
  const exists = await User.findOne({ $or: [{ username: username.toLowerCase() }, { email: email.toLowerCase() }] });
  if (exists) {
    // Cleanup uploaded file if exists
    await removeUploadedFile(req.file?.path);
    throw new ApiError(409, "User with email or username already exists");
  }

  if (!req.file?.path) {
    throw new ApiError(400, "Avatar file is required");
  }

  const localPath = "/" + path.relative("public", req.file.path).replace(/\\/g, "/");

  const user = await User.create({
    username: username.toLowerCase(),
    email: email.toLowerCase(),
    fullName,
    avatar: localPath,
    contact,
    age: parseInt(age),
    password,
  });

  const clean = await User.findById(user._id).select("-password -refreshToken");

  logSecurityEvent("USER_REGISTERED", {
    userId: user._id,
    email: user.email,
    ip: req.ip,
  });

  return res
    .status(201)
    .json(new ApiResponse(201, clean, "User registered successfully"));
});

/**
 * Login user
 * POST /api/v1/users/login
 */
export const loginUser = asyncHandler(async (req, res) => {
  const { email, username, password } = req.body;

  if (!(email || username)) {
    throw new ApiError(400, "Username or email is required");
  }

  // Build query dynamically - only include fields that are provided
  const queryConditions = [];
  if (username) queryConditions.push({ username: username.toLowerCase() });
  if (email) queryConditions.push({ email: email.toLowerCase() });

  const user = await User.findOne({ $or: queryConditions });

  if (!user) {
    logFailedLogin(email || username, req.ip, "User not found");
    throw new ApiError(404, "User not found");
  }

  if (!user.isActive) {
    logFailedLogin(email || username, req.ip, "User account is disabled");
    throw new ApiError(403, "Your account is disabled. Contact support.");
  }

  const isPasswordValid = await user.isPasswordCorrect(password);
  if (!isPasswordValid) {
    logFailedLogin(email || username, req.ip, "Incorrect password");
    throw new ApiError(401, "Incorrect password");
  }

  const { accessToken, refreshToken } = await generateAccessAndRefreshToken(User, user._id);
  const clean = await User.findById(user._id).select("-password -refreshToken");

  logSuccessfulLogin(user._id, user.email, req.ip);

  return res
    .status(200)
    .cookie("accessToken", accessToken, cookieOptions)
    .cookie("refreshToken", refreshToken, refreshCookieOptions)
    .json(
      new ApiResponse(200, { user: clean, accessToken, refreshToken }, "User logged in successfully")
    );
});

/**
 * Logout user
 * POST /api/v1/users/logout
 */
export const logoutUser = asyncHandler(async (req, res) => {
  await User.findByIdAndUpdate(req.user._id, { $unset: { refreshToken: 1 } });

  logSecurityEvent("USER_LOGOUT", {
    userId: req.user._id,
    email: req.user.email,
    ip: req.ip,
  });

  return res
    .status(200)
    .clearCookie("accessToken", cookieOptions)
    .clearCookie("refreshToken", refreshCookieOptions)
    .json(new ApiResponse(200, {}, "User logged out successfully"));
});

/**
 * Refresh access token
 * POST /api/v1/users/refresh-token
 */
export const refreshAccessToken = asyncHandler(async (req, res) => {
  const incoming = req.cookies.refreshToken || req.body.refreshToken;

  if (!incoming) {
    throw new ApiError(401, "Unauthorized request");
  }

  let decoded;
  try {
    decoded = jwt.verify(incoming, process.env.REFRESH_TOKEN_SECRET);
  } catch (err) {
    throw new ApiError(401, "Invalid or expired refresh token");
  }

  const user = await User.findById(decoded._id);
  if (!user) {
    throw new ApiError(401, "Invalid refresh token");
  }

  if (incoming !== user.refreshToken) {
    throw new ApiError(401, "Refresh token expired or invalid");
  }

  const { accessToken, refreshToken } = await generateAccessAndRefreshToken(User, user._id);

  return res
    .status(200)
    .cookie("accessToken", accessToken, cookieOptions)
    .cookie("refreshToken", refreshToken, refreshCookieOptions)
    .json(new ApiResponse(200, { accessToken, refreshToken }, "Access token refreshed"));
});

/**
 * Change current password
 * POST /api/v1/users/change-password
 */
export const changeCurrentPassword = asyncHandler(async (req, res) => {
  const { oldPassword, newPassword } = req.body;
  const user = await User.findById(req.user._id);

  const isPasswordValid = await user.isPasswordCorrect(oldPassword);
  if (!isPasswordValid) {
    throw new ApiError(400, "Invalid old password");
  }

  user.password = newPassword;
  user.refreshToken = undefined;
  await user.save({ validateBeforeSave: false });

  logSecurityEvent("PASSWORD_CHANGED", {
    userId: req.user._id,
    email: req.user.email,
    ip: req.ip,
  });

  return res
    .status(200)
    .json(new ApiResponse(200, {}, "Password changed successfully"));
});

/**
 * Get current user
 * POST /api/v1/users/current-user
 */
export const getCurrentUser = asyncHandler(async (req, res) => {
  if (!req.user) {
    throw new ApiError(401, "User not authenticated");
  }

  return res
    .status(200)
    .json(new ApiResponse(200, req.user, "Current user fetched successfully"));
});

/**
 * Update user profile
 * PUT /api/v1/users/update-profile
 */
export const updateProfile = asyncHandler(async (req, res) => {
  if (!req.user) {
    throw new ApiError(401, "User not authenticated");
  }

  const {
    fullName,
    username,
    contact,
    age,
    bloodGroup,
    medicalInfo,
    medicalConditions,
    allergies,
    emergencyContact1,
    emergencyContact2,
    address,
    city,
    state,
    pincode,
    shareMedicalInfo,
    shareLocation,
  } = req.body;

  // Build update object with only provided fields
  const updateFields = {};
  
  if (fullName !== undefined) updateFields.fullName = fullName;
  if (username !== undefined) {
    // Check if username is taken by another user
    const normalizedUsername = username.toLowerCase();
    const existingUser = await User.findOne({ username: normalizedUsername, _id: { $ne: req.user._id } });
    if (existingUser) {
      await removeUploadedFile(req.file?.path);
      throw new ApiError(400, "Username already taken");
    }
    updateFields.username = normalizedUsername;
  }
  if (contact !== undefined) updateFields.contact = contact;
  if (age !== undefined) updateFields.age = age;
  if (bloodGroup !== undefined) updateFields.bloodGroup = bloodGroup;
  if (medicalInfo !== undefined) updateFields.medicalInfo = medicalInfo;
  if (medicalConditions !== undefined) {
    let parsedMedicalConditions = medicalConditions;

    if (typeof medicalConditions === "string") {
      const trimmed = medicalConditions.trim();
      if (!trimmed) {
        parsedMedicalConditions = [];
      } else {
        try {
          parsedMedicalConditions = JSON.parse(trimmed);
        } catch {
          parsedMedicalConditions = trimmed
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
        }
      }
    }

    if (!Array.isArray(parsedMedicalConditions)) {
      await removeUploadedFile(req.file?.path);
      throw new ApiError(400, "medicalConditions must be an array or valid JSON array");
    }

    updateFields.medicalConditions = parsedMedicalConditions
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }
  if (allergies !== undefined) updateFields.allergies = allergies;
  if (emergencyContact1 !== undefined) updateFields.emergencyContact1 = emergencyContact1;
  if (emergencyContact2 !== undefined) updateFields.emergencyContact2 = emergencyContact2;
  if (address !== undefined) updateFields.address = address;
  if (city !== undefined) updateFields.city = city;
  if (state !== undefined) updateFields.state = state;
  if (pincode !== undefined) updateFields.pincode = pincode;
  if (shareMedicalInfo !== undefined) updateFields.shareMedicalInfo = shareMedicalInfo;
  if (shareLocation !== undefined) updateFields.shareLocation = shareLocation;

  // Handle avatar upload if present
  if (req.file) {
    updateFields.avatar = `/user_imgs/${req.file.filename}`;
  }

  const updatedUser = await User.findByIdAndUpdate(
    req.user._id,
    { $set: updateFields },
    { new: true }
  ).select("-password -refreshToken");

  if (!updatedUser) {
    await removeUploadedFile(req.file?.path);
    throw new ApiError(404, "User not found");
  }

  return res
    .status(200)
    .json(new ApiResponse(200, updatedUser, "Profile updated successfully"));
});

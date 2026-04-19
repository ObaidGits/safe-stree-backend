import { ApiError } from "../utils/ApiError.js";
import { asyncHandler } from "../utils/asyncHandler.js";
import jwt from "jsonwebtoken";
import { User } from "../models/user.model.js";
import { Admin } from "../models/admin.model.js";

export const verifyJWT = asyncHandler(async (req, res, next) => {
  const authHeader = req.header("Authorization");
  const cookieToken = req.cookies?.accessToken;

  let token = null;

  if (authHeader?.startsWith("Bearer ")) token = authHeader.split(" ")[1];
  else if (cookieToken) token = cookieToken;

  if (!token) throw new ApiError(401, "Unauthorized request");

  let decoded;
  try {
    decoded = jwt.verify(token, process.env.ACCESS_TOKEN_SECRET);
  } catch (err) {
    if (err?.name === "TokenExpiredError")
      throw new ApiError(401, "Token expired");
    throw new ApiError(401, "Invalid access token");
  }

  // Admin token
  if (decoded?.officerName) {
    const admin = await Admin.findById(decoded._id).select(
      "-password -refreshToken"
    );
    if (!admin) throw new ApiError(401, "Invalid access token");
    if (!admin.isActive) throw new ApiError(403, "Admin account is disabled");
    req.admin = admin;
    return next();
  }

  // User token
  const user = await User.findById(decoded._id).select(
    "-password -refreshToken"
  );
  if (!user) throw new ApiError(401, "Invalid access token");
  if (!user.isActive) throw new ApiError(403, "User account is disabled");

  req.user = user;
  next();
});

export const requireAdmin = (req, res, next) => {
  if (!req.admin) {
    throw new ApiError(403, "Admin access required");
  }
  next();
};

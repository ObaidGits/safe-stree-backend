import { ApiError } from "../utils/ApiError.js";

/**
 * API Key authentication middleware for CCTV/ML backend routes
 * Validates X-API-Key header against CCTV_API_KEY environment variable
 */
export const verifyApiKey = (req, res, next) => {
  const apiKey = req.header("X-API-Key");
  const validKey = process.env.CCTV_API_KEY;

  if (!validKey) {
    console.error("⚠️ CCTV_API_KEY not configured in environment");
    throw new ApiError(500, "Server configuration error");
  }

  if (!apiKey) {
    throw new ApiError(401, "API key required");
  }

  if (apiKey !== validKey) {
    throw new ApiError(403, "Invalid API key");
  }

  next();
};

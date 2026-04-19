import { ApiError } from "./ApiError.js";

/**
 * Generate access and refresh tokens for a user or admin
 * @param {Object} model - Mongoose model (User or Admin)
 * @param {string} id - Document ID
 * @returns {Promise<{accessToken: string, refreshToken: string}>}
 */
export const generateAccessAndRefreshToken = async (model, id) => {
  const doc = await model.findById(id);
  if (!doc) throw new ApiError(404, "Account not found while generating tokens");

  const accessToken = doc.generateAccessToken();
  const refreshToken = doc.generateRefreshToken();

  doc.refreshToken = refreshToken;
  await doc.save({ validateBeforeSave: false });

  return { accessToken, refreshToken };
};

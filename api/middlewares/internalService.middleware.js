import { ApiError } from "../utils/ApiError.js";

const getServiceTokenFromRequest = (req) => {
  const directToken = req.header("X-Internal-Service-Token");
  if (directToken) {
    return directToken;
  }

  const authHeader = req.header("Authorization");
  if (!authHeader) {
    return null;
  }

  const [scheme, token] = authHeader.split(" ");
  if (scheme?.toLowerCase() !== "bearer" || !token) {
    return null;
  }

  return token;
};

export const verifyInternalService = (req, res, next) => {
  const providedToken = getServiceTokenFromRequest(req);
  const validToken = process.env.INTERNAL_ML_SERVICE_TOKEN;

  if (!validToken) {
    throw new ApiError(500, "Internal service token is not configured");
  }

  if (!providedToken) {
    throw new ApiError(401, "Internal service token required");
  }

  if (providedToken !== validToken) {
    throw new ApiError(403, "Invalid internal service token");
  }

  req.internalService = {
    name: req.header("X-Internal-Service-Name") || "unknown-internal-service",
  };

  next();
};

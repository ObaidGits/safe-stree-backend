import rateLimit from "express-rate-limit";

/**
 * Rate limiter for authentication routes (login, register)
 * Prevents brute force attacks
 */
export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 10, // 10 attempts per window
  message: {
    statusCode: 429,
    success: false,
    message: "Too many attempts. Please try again after 15 minutes.",
  },
  standardHeaders: true,
  legacyHeaders: false,
});

/**
 * Rate limiter for SOS creation
 * Prevents spam alerts while allowing legitimate emergencies
 */
export const sosLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 5, // 5 SOS per minute
  message: {
    statusCode: 429,
    success: false,
    message: "Too many SOS alerts. Please wait before sending another.",
  },
  standardHeaders: true,
  legacyHeaders: false,
});

/**
 * General API rate limiter
 */
export const generalLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 100, // 100 requests per minute
  message: {
    statusCode: 429,
    success: false,
    message: "Too many requests. Please slow down.",
  },
  standardHeaders: true,
  legacyHeaders: false,
});

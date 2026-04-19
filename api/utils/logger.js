import winston from "winston";
import DailyRotateFile from "winston-daily-rotate-file";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const logsDir = path.join(__dirname, "../logs");

// Custom format for console
const consoleFormat = winston.format.combine(
  winston.format.colorize(),
  winston.format.timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
  winston.format.printf(({ timestamp, level, message, ...meta }) => {
    const metaStr = Object.keys(meta).length ? JSON.stringify(meta) : "";
    return `[${timestamp}] ${level}: ${message} ${metaStr}`;
  })
);

// JSON format for files
const fileFormat = winston.format.combine(
  winston.format.timestamp(),
  winston.format.json()
);

// Security events logger (login attempts, password changes, SOS alerts)
const securityTransport = new DailyRotateFile({
  filename: path.join(logsDir, "security-%DATE%.log"),
  datePattern: "YYYY-MM-DD",
  maxSize: "20m",
  maxFiles: "30d",
  format: fileFormat,
});

// Error logger
const errorTransport = new DailyRotateFile({
  filename: path.join(logsDir, "error-%DATE%.log"),
  datePattern: "YYYY-MM-DD",
  level: "error",
  maxSize: "20m",
  maxFiles: "30d",
  format: fileFormat,
});

// Combined logger
const combinedTransport = new DailyRotateFile({
  filename: path.join(logsDir, "combined-%DATE%.log"),
  datePattern: "YYYY-MM-DD",
  maxSize: "20m",
  maxFiles: "14d",
  format: fileFormat,
});

// Main application logger
export const logger = winston.createLogger({
  level: process.env.NODE_ENV === "production" ? "info" : "debug",
  transports: [
    new winston.transports.Console({ format: consoleFormat }),
    combinedTransport,
    errorTransport,
  ],
});

// Security-specific logger for audit trail
export const securityLogger = winston.createLogger({
  level: "info",
  transports: [
    securityTransport,
    new winston.transports.Console({ format: consoleFormat }),
  ],
});

/**
 * Log security events (login, logout, password change, SOS)
 */
export const logSecurityEvent = (event, data) => {
  securityLogger.info(event, {
    ...data,
    timestamp: new Date().toISOString(),
  });
};

/**
 * Log SOS alert creation
 */
export const logSOSAlert = (alertType, alertId, location, userId = null) => {
  securityLogger.warn("SOS_ALERT_CREATED", {
    alertType,
    alertId,
    location,
    userId,
    timestamp: new Date().toISOString(),
  });
};

/**
 * Log failed login attempt
 */
export const logFailedLogin = (identifier, ip, reason) => {
  securityLogger.warn("FAILED_LOGIN", {
    identifier,
    ip,
    reason,
    timestamp: new Date().toISOString(),
  });
};

/**
 * Log successful login
 */
export const logSuccessfulLogin = (userId, email, ip) => {
  securityLogger.info("SUCCESSFUL_LOGIN", {
    userId,
    email,
    ip,
    timestamp: new Date().toISOString(),
  });
};

export default logger;

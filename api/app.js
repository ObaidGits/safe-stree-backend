import express from "express";
import dotenv from "dotenv";
import cookieParser from "cookie-parser";
import cors from "cors";
import helmet from "helmet";
import compression from "compression";
import mongoSanitize from "express-mongo-sanitize";
import { createServer } from "http";
import connectDB from "./db/index.js";
import path from "path";
import { fileURLToPath } from "url";
import { initializeSocket } from "./socket/index.js";
import { generalLimiter } from "./middlewares/rateLimit.middleware.js";
import logger from "./utils/logger.js";

// Load env vars
dotenv.config({ path: "./.env" });

const app = express();
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ---------- SECURITY MIDDLEWARE ----------
// Helmet - Set security HTTP headers
app.use(
  helmet({
    crossOriginResourcePolicy: { policy: "cross-origin" }, // Allow static files
    contentSecurityPolicy: false, // Disable CSP for API server
  })
);

// Compression - Gzip responses
app.use(compression());

// NoSQL Injection Prevention
app.use(mongoSanitize());

// ---------- CORS (SAFE + FLEXIBLE) ----------
const allowedOrigins = (process.env.CORS_ORIGIN || "")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

app.use(
  cors({
    origin: allowedOrigins.length ? allowedOrigins : true,
    credentials: true,
  })
);

// ---------- BODY PARSING ----------
app.use(express.json({ limit: "16kb" }));
app.use(express.urlencoded({ extended: true, limit: "16kb" }));
app.use(cookieParser());
app.set("trust proxy", 1);

// ---------- GENERAL RATE LIMITING ----------
app.use("/api", generalLimiter);

// ---------- STATIC FILES ----------
app.use("/cctv_sos", express.static(path.join(__dirname, "public/cctv_sos")));
app.use("/web_sos", express.static(path.join(__dirname, "public/web_sos")));
app.use("/user_imgs", express.static(path.join(__dirname, "public/user_imgs")));

// ---------- ROUTES ----------
import userRouter from "./routes/user.routes.js";
import adminRouter from "./routes/admin.routes.js";
import webSosRouter from "./routes/websos.routes.js";
import cctvSosRouter from "./routes/cctvsos.routes.js";

app.use("/api/v1/users", userRouter);
app.use("/api/v1/admin", adminRouter);
app.use("/api/v1/sos", webSosRouter);
app.use("/api/v1/cctv", cctvSosRouter);

// ---------- HEALTH ----------
app.get("/", (req, res) => res.send("🚀 Backend Running"));
app.get("/health", (req, res) =>
  res.status(200).json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  })
);

// ---------- 404 HANDLER ----------
app.use((req, res) => {
  res.status(404).json({
    statusCode: 404,
    success: false,
    message: `Route ${req.method} ${req.originalUrl} not found`,
  });
});

// ---------- ERROR FALLBACK ----------
app.use((err, req, res, next) => {
  const status = err.statusCode || 500;
  
  // Only log server errors (5xx) and unexpected client errors
  // Skip logging expected 401 auth checks (e.g., /current-user)
  const isExpected401 = status === 401 && req.originalUrl.includes('current-user');
  
  if (!isExpected401) {
    logger.error(`API Error ${err.message}`, {
      method: req.method,
      url: req.originalUrl,
      status,
      stack: process.env.NODE_ENV === "development" ? err.stack : undefined,
      ip: req.ip,
    });
  }

  res.status(status).json({
    statusCode: status,
    success: false,
    message: err.message || "Internal server error",
    errors: err.error || [],
    ...(process.env.NODE_ENV === "development" && { stack: err.stack }),
  });
});

// ---------- SOCKET SERVER ----------
const httpServer = createServer(app);

// ---------- BOOT ----------
connectDB()
  .then(() => {
    // Initialize Socket.IO after DB connection
    initializeSocket(httpServer, allowedOrigins);
    
    const PORT = process.env.PORT || 8000;
    httpServer.listen(PORT, () => {
      logger.info(`✅ Server started on port ${PORT}`);
      console.log(`✅ Server running on port ${PORT}`);
    });
  })
  .catch((err) => {
    logger.error("MongoDB connection failed", { error: err.message });
    console.error("❌ MongoDB failed!", err);
    process.exit(1);
  });

// ---------- GRACEFUL SHUTDOWN ----------
process.on("SIGTERM", () => {
  logger.info("SIGTERM received. Shutting down gracefully...");
  httpServer.close(() => {
    logger.info("Server closed");
    process.exit(0);
  });
});

process.on("unhandledRejection", (reason, promise) => {
  logger.error("Unhandled Rejection", { reason: reason?.message || reason });
  console.error("Unhandled Rejection:", reason);
});

process.on("uncaughtException", (err) => {
  logger.error("Uncaught Exception", { error: err.message, stack: err.stack });
  console.error("Uncaught Exception:", err);
  process.exit(1);
});

import path from "path";
import { fileURLToPath } from "url";
import { jest, describe, it, expect, beforeEach } from "@jest/globals";
import request from "supertest";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

process.env.NODE_ENV = "test";

const mockLogger = {
  info: jest.fn(),
  error: jest.fn(),
  warn: jest.fn(),
};

const mockJwt = {
  verify: jest.fn(),
};

const mockUserModel = {
  findOne: jest.fn(),
  findById: jest.fn(),
  findByIdAndUpdate: jest.fn(),
  create: jest.fn(),
  countDocuments: jest.fn(),
  find: jest.fn(),
};

const mockAdminModel = {
  findOne: jest.fn(),
  findById: jest.fn(),
  findByIdAndUpdate: jest.fn(),
  create: jest.fn(),
  countDocuments: jest.fn(),
  find: jest.fn(),
};

const mockWebAlertModel = {
  findOne: jest.fn(),
  findByIdAndDelete: jest.fn(),
  findByIdAndUpdate: jest.fn(),
  create: jest.fn(),
  countDocuments: jest.fn(),
  find: jest.fn(),
  aggregate: jest.fn(),
};

const mockCctvAlertModel = {
  findOne: jest.fn(),
  findByIdAndDelete: jest.fn(),
  findByIdAndUpdate: jest.fn(),
  create: jest.fn(),
  countDocuments: jest.fn(),
  find: jest.fn(),
  aggregate: jest.fn(),
};

const mockBroadcastNewAlert = jest.fn();
const mockInitializeSocket = jest.fn();
const mockRemoveCCTVImage = jest.fn().mockResolvedValue(undefined);
const mockBuildCCTVAlertDocument = jest.fn();
const mockBuildCCTVAlertLogContext = jest.fn(() => ({}));

const passthroughMiddleware = () => (req, res, next) => next();

const mockUserMulter = {
  single: jest.fn(() => (req, _res, next) => {
    req.file = { path: path.resolve(__dirname, "../public/user_imgs/test-avatar.jpg") };
    next();
  }),
};

const mockCctvMulter = {
  single: jest.fn(() => (req, _res, next) => {
    req.savedFileName = "cctv_sos_test.jpg";
    next();
  }),
};

const createSelectDoc = (doc) => ({
  select: jest.fn().mockResolvedValue(doc),
});

const createListQuery = (result) => ({
  select: jest.fn().mockReturnThis(),
  populate: jest.fn().mockReturnThis(),
  sort: jest.fn().mockReturnThis(),
  skip: jest.fn().mockReturnThis(),
  limit: jest.fn().mockResolvedValue(result),
});

const createAuthDoc = ({
  _id,
  accessToken,
  refreshToken,
  email,
  username,
  fullName,
  officerName,
  policeStation,
}) => ({
  _id,
  email,
  username,
  fullName,
  officerName,
  policeStation,
  isActive: true,
  refreshToken: undefined,
  generateAccessToken: jest.fn(() => accessToken),
  generateRefreshToken: jest.fn(() => refreshToken),
  isPasswordCorrect: jest.fn().mockResolvedValue(true),
  save: jest.fn().mockResolvedValue(undefined),
});

const createWebAlertDoc = (overrides = {}) => {
  const doc = {
    _id: overrides._id || "web-alert-1",
    userId: overrides.userId || "user-1",
    status: overrides.status || "active",
    createdAt: overrides.createdAt || new Date("2026-01-01T00:00:00.000Z"),
    location: overrides.location || { type: "Point", coordinates: [77.1, 28.6] },
    liveAddress: overrides.liveAddress || "Address unavailable (API key missing)",
    ...overrides,
  };

  doc.toObject = () => ({ ...doc });
  return doc;
};

const createCctvAlertDoc = (overrides = {}) => {
  const doc = {
    _id: overrides._id || "cctv-alert-1",
    sos_img: overrides.sos_img || "cctv_sos_test.jpg",
    eventId: overrides.eventId || "event-001",
    source: overrides.source || "CCTV",
    status: overrides.status || "active",
    createdAt: overrides.createdAt || new Date("2026-01-02T00:00:00.000Z"),
    location: overrides.location || { type: "Point", coordinates: [77.2, 28.7] },
    ...overrides,
  };

  doc.toObject = () => ({ ...doc });
  return doc;
};

await jest.unstable_mockModule("jsonwebtoken", () => ({ default: mockJwt }));
await jest.unstable_mockModule("../utils/logger.js", () => ({
  default: mockLogger,
  logger: mockLogger,
  securityLogger: mockLogger,
  logSecurityEvent: jest.fn(),
  logSOSAlert: jest.fn(),
  logFailedLogin: jest.fn(),
  logSuccessfulLogin: jest.fn(),
}));
await jest.unstable_mockModule("../socket/index.js", () => ({
  initializeSocket: mockInitializeSocket,
  broadcastNewAlert: mockBroadcastNewAlert,
}));
await jest.unstable_mockModule("../models/user.model.js", () => ({ User: mockUserModel }));
await jest.unstable_mockModule("../models/admin.model.js", () => ({ Admin: mockAdminModel }));
await jest.unstable_mockModule("../models/websos.model.js", () => ({ SOSAlert: mockWebAlertModel }));
await jest.unstable_mockModule("../models/cctvsos.model.js", () => ({ CCTVSOSAlert: mockCctvAlertModel }));
await jest.unstable_mockModule("../middlewares/rateLimit.middleware.js", () => ({
  generalLimiter: passthroughMiddleware(),
  authLimiter: passthroughMiddleware(),
  sosLimiter: passthroughMiddleware(),
}));
await jest.unstable_mockModule("../middlewares/apiKey.middleware.js", () => ({
  verifyApiKey: passthroughMiddleware(),
}));
await jest.unstable_mockModule("../middlewares/internalService.middleware.js", () => ({
  verifyInternalService: passthroughMiddleware(),
}));
await jest.unstable_mockModule("../middlewares/user.middleware.js", () => ({
  userMulter: mockUserMulter,
}));
await jest.unstable_mockModule("../middlewares/cctvsos.multer.js", () => ({
  uploadCCTVSOS: mockCctvMulter,
}));
await jest.unstable_mockModule("../utils/cctvAlertMetadata.js", () => ({
  buildCCTVAlertDocument: mockBuildCCTVAlertDocument,
  buildCCTVAlertLogContext: mockBuildCCTVAlertLogContext,
  removeCCTVImage: mockRemoveCCTVImage,
  parseMaybeJson: jest.fn(),
}));

const { app } = await import("../app.js");

const resetMocks = () => {
  jest.clearAllMocks();
  process.env.OPENCAGE_API_KEY = "";

  mockJwt.verify.mockImplementation((token) => {
    if (token === "user-token" || token === "refresh-user-token") {
      return { _id: "user-1" };
    }

    if (token === "stored-refresh") {
      return { _id: "user-1" };
    }

    if (token === "admin-token") {
      return { _id: "admin-1", officerName: "Inspector Ria", policeStation: "North Gate" };
    }

    throw new Error("invalid token");
  });

  mockUserModel.findOne.mockResolvedValue(null);
  mockUserModel.findById.mockImplementation(() => createSelectDoc({
    _id: "user-1",
    username: "alice",
    email: "alice@example.com",
    fullName: "Alice Doe",
    isActive: true,
  }));
  mockUserModel.findByIdAndUpdate.mockResolvedValue({ _id: "user-1" });
  mockUserModel.create.mockResolvedValue(createWebAlertDoc({ _id: "user-created" }));
  mockUserModel.countDocuments.mockResolvedValue(3);
  mockUserModel.find.mockReturnValue(createListQuery([]));

  mockAdminModel.findOne.mockResolvedValue(null);
  mockAdminModel.findById.mockImplementation(() => createSelectDoc({
    _id: "admin-1",
    officerName: "Inspector Ria",
    email: "admin@example.com",
    policeStation: "North Gate",
    isActive: true,
  }));
  mockAdminModel.findByIdAndUpdate.mockResolvedValue({ _id: "admin-1" });
  mockAdminModel.create.mockResolvedValue({ _id: "admin-created" });
  mockAdminModel.countDocuments.mockResolvedValue(2);
  mockAdminModel.find.mockReturnValue(createListQuery([]));

  mockWebAlertModel.findOne.mockResolvedValue(null);
  mockWebAlertModel.findByIdAndDelete.mockResolvedValue(createWebAlertDoc());
  mockWebAlertModel.findByIdAndUpdate.mockResolvedValue(createWebAlertDoc({ status: "resolved" }));
  mockWebAlertModel.create.mockResolvedValue(createWebAlertDoc());
  mockWebAlertModel.countDocuments.mockResolvedValue(4);
  mockWebAlertModel.find.mockReturnValue(createListQuery([createWebAlertDoc()]));
  mockWebAlertModel.aggregate.mockImplementation(async (pipeline) => {
    if (pipeline.some((stage) => stage.$count)) {
      return [{ count: 1 }];
    }

    return [
      {
        _id: "web-alert-1",
        createdAt: new Date("2026-01-01T00:00:00.000Z"),
        liveAddress: "City Center",
        status: "active",
        userId: { _id: "user-1", fullName: "Alice Doe" },
      },
    ];
  });

  mockCctvAlertModel.findOne.mockResolvedValue(null);
  mockCctvAlertModel.findByIdAndDelete.mockResolvedValue(createCctvAlertDoc());
  mockCctvAlertModel.findByIdAndUpdate.mockResolvedValue(createCctvAlertDoc({ status: "resolved" }));
  mockCctvAlertModel.create.mockResolvedValue(createCctvAlertDoc());
  mockCctvAlertModel.countDocuments.mockResolvedValue(2);
  mockCctvAlertModel.find.mockReturnValue(createListQuery([createCctvAlertDoc()]));
  mockCctvAlertModel.aggregate.mockImplementation(async (pipeline) => {
    if (pipeline.some((stage) => stage.$count)) {
      return [{ count: 1 }];
    }

    return [
      {
        _id: "cctv-alert-1",
        createdAt: new Date("2026-01-02T00:00:00.000Z"),
        source: "CCTV",
        status: "active",
        eventId: "event-001",
      },
    ];
  });

  mockBuildCCTVAlertDocument.mockImplementation(({ body, savedFileName, ingestSource }) => {
    return createCctvAlertDoc({
      sos_img: savedFileName,
      eventId: body.eventId || "event-001",
      source: body.source || "CCTV",
      ingestSource,
      location: {
        type: "Point",
        coordinates: [Number(body.longitude), Number(body.latitude)],
      },
    });
  });
};

beforeEach(() => {
  resetMocks();
});

describe("backend api e2e", () => {
  it("returns health and a clean 404 response", async () => {
    const health = await request(app).get("/health");
    expect(health.status).toBe(200);
    expect(health.body.status).toBe("healthy");

    const notFound = await request(app).get("/api/v1/does-not-exist");
    expect(notFound.status).toBe(404);
    expect(notFound.body.message).toContain("Route GET /api/v1/does-not-exist not found");
  });

  it("registers, logs in, reads current user, changes password, and logs out a user", async () => {
    mockUserModel.create.mockResolvedValue({ _id: "user-1" });
    mockUserModel.findById
      .mockImplementationOnce(() => createSelectDoc({
        _id: "user-1",
        username: "alice_safety",
        email: "alice@example.com",
        fullName: "Alice Doe",
        avatar: "/user_imgs/test-avatar.jpg",
        isActive: true,
      }));

    const register = await request(app)
      .post("/api/v1/users/register")
      .send({
        username: "alice_safety",
        email: "alice@example.com",
        fullName: "Alice Doe",
        contact: "+911234567890",
        age: 24,
        password: "Passw0rd",
      });

    expect(register.status).toBe(201);
    expect(register.body.success).toBe(true);
    expect(register.body.data.email).toBe("alice@example.com");

    const loginDoc = createAuthDoc({
      _id: "user-1",
      email: "alice@example.com",
      username: "alice_safety",
      fullName: "Alice Doe",
      accessToken: "user-access",
      refreshToken: "user-refresh",
    });

    mockUserModel.findOne.mockResolvedValueOnce(loginDoc);
    mockUserModel.findById
      .mockImplementationOnce(() => loginDoc)
      .mockImplementationOnce(() => createSelectDoc({
        _id: "user-1",
        username: "alice_safety",
        email: "alice@example.com",
        fullName: "Alice Doe",
        isActive: true,
      }));

    const login = await request(app)
      .post("/api/v1/users/login")
      .send({ email: "alice@example.com", password: "Passw0rd" });

    expect(login.status).toBe(200);
    expect(login.body.data.user.email).toBe("alice@example.com");
    expect(login.headers["set-cookie"]).toEqual(expect.arrayContaining([
      expect.stringContaining("accessToken="),
      expect.stringContaining("refreshToken="),
    ]));

    mockUserModel.findById.mockReset();
    mockUserModel.findById.mockImplementation(() => createSelectDoc({
      _id: "user-1",
      username: "alice_safety",
      email: "alice@example.com",
      fullName: "Alice Doe",
      isActive: true,
    }));

    const current = await request(app)
      .post("/api/v1/users/current-user")
      .set("Authorization", "Bearer user-token");

    expect(current.status).toBe(200);
    expect(current.body.data._id).toBe("user-1");

    mockUserModel.findById.mockReset();
    mockUserModel.findById
      .mockImplementationOnce(() => createSelectDoc({
        _id: "user-1",
        username: "alice_safety",
        email: "alice@example.com",
        fullName: "Alice Doe",
        isActive: true,
      }))
      .mockImplementationOnce(() => ({
        isPasswordCorrect: jest.fn().mockResolvedValue(true),
        save: jest.fn().mockResolvedValue(undefined),
      }));

    const changePassword = await request(app)
      .post("/api/v1/users/change-password")
      .set("Authorization", "Bearer user-token")
      .send({ oldPassword: "OldPassw0rd", newPassword: "NewPassw0rd" });

    expect(changePassword.status).toBe(200);
    expect(changePassword.body.message).toBe("Password changed successfully");

    mockUserModel.findById.mockReset();
    mockUserModel.findById.mockImplementation(() => createSelectDoc({
      _id: "user-1",
      username: "alice_safety",
      email: "alice@example.com",
      fullName: "Alice Doe",
      isActive: true,
    }));

    const logout = await request(app)
      .post("/api/v1/users/logout")
      .set("Authorization", "Bearer user-token");

    expect(logout.status).toBe(200);
    expect(logout.body.message).toBe("User logged out successfully");
  });

  it("refreshes a user token", async () => {
    const refreshDoc = {
      _id: "user-1",
      refreshToken: "stored-refresh",
      generateAccessToken: jest.fn(() => "user-access-2"),
      generateRefreshToken: jest.fn(() => "user-refresh-2"),
      save: jest.fn().mockResolvedValue(undefined),
    };

    mockUserModel.findById
      .mockImplementationOnce(() => refreshDoc)
      .mockImplementationOnce(() => refreshDoc);

    const refresh = await request(app)
      .post("/api/v1/users/refresh-token")
      .send({ refreshToken: "stored-refresh" });

    expect(refresh.status).toBe(200);
    expect(refresh.body.data.accessToken).toBe("user-access-2");
  });

  it("registers, logs in, reads current admin, and logs out an admin", async () => {
    mockAdminModel.create.mockResolvedValue({ _id: "admin-1" });
    mockAdminModel.findById
      .mockImplementationOnce(() => createSelectDoc({
        _id: "admin-1",
        officerName: "Inspector Ria",
        email: "admin@example.com",
        policeStation: "North Gate",
        isActive: true,
      }));

    const register = await request(app)
      .post("/api/v1/admin/register")
      .send({
        officerName: "Inspector Ria",
        email: "admin@example.com",
        policeStation: "North Gate",
        password: "AdminPass1",
      });

    expect(register.status).toBe(201);
    expect(register.body.data.email).toBe("admin@example.com");

    const loginDoc = createAuthDoc({
      _id: "admin-1",
      email: "admin@example.com",
      officerName: "Inspector Ria",
      policeStation: "North Gate",
      accessToken: "admin-access-2",
      refreshToken: "admin-refresh-2",
    });

    mockAdminModel.findOne.mockResolvedValueOnce(loginDoc);
    mockAdminModel.findById
      .mockImplementationOnce(() => loginDoc)
      .mockImplementationOnce(() => createSelectDoc({
        _id: "admin-1",
        officerName: "Inspector Ria",
        email: "admin@example.com",
        policeStation: "North Gate",
        isActive: true,
      }));

    const login = await request(app)
      .post("/api/v1/admin/login")
      .send({ email: "admin@example.com", password: "AdminPass1" });

    expect(login.status).toBe(200);
    expect(login.body.data.admin.email).toBe("admin@example.com");

    mockAdminModel.findById.mockReset();
    mockAdminModel.findById.mockImplementation(() => createSelectDoc({
      _id: "admin-1",
      officerName: "Inspector Ria",
      email: "admin@example.com",
      policeStation: "North Gate",
      isActive: true,
    }));

    const current = await request(app)
      .post("/api/v1/admin/current-admin")
      .set("Authorization", "Bearer admin-token");

    expect(current.status).toBe(200);
    expect(current.body.data._id).toBe("admin-1");

    mockAdminModel.findById.mockReset();
    mockAdminModel.findById.mockImplementation(() => createSelectDoc({
      _id: "admin-1",
      officerName: "Inspector Ria",
      email: "admin@example.com",
      policeStation: "North Gate",
      isActive: true,
    }));

    const logout = await request(app)
      .post("/api/v1/admin/logout")
      .set("Authorization", "Bearer admin-token");

    expect(logout.status).toBe(200);
    expect(logout.body.message).toBe("Admin logged out successfully");
  });

  it("returns management overview and searchable alerts for admins", async () => {
    mockUserModel.countDocuments.mockResolvedValueOnce(10).mockResolvedValueOnce(7);
    mockAdminModel.countDocuments.mockResolvedValueOnce(3).mockResolvedValueOnce(2);
    mockWebAlertModel.countDocuments.mockResolvedValueOnce(5).mockResolvedValueOnce(4);
    mockCctvAlertModel.countDocuments.mockResolvedValueOnce(6).mockResolvedValueOnce(3);

    const overview = await request(app)
      .get("/api/v1/admin/management/overview")
      .set("Authorization", "Bearer admin-token");

    expect(overview.status).toBe(200);
    expect(overview.body.data.users.total).toBe(10);
    expect(overview.body.data.alerts.cctv.resolved).toBe(3);

    const alerts = await request(app)
      .get("/api/v1/admin/management/alerts")
      .query({ search: "bridge", status: "active", kind: "all", page: 1, limit: 10 })
      .set("Authorization", "Bearer admin-token");

    expect(alerts.status).toBe(200);
    expect(alerts.body.data.pagination.total).toBe(2);
    expect(alerts.body.data.filters.search).toBe("bridge");
    expect(alerts.body.data.alerts).toHaveLength(2);
  });

  it("deletes managed web and cctv alerts from the admin panel route", async () => {
    mockWebAlertModel.findByIdAndDelete.mockResolvedValueOnce(createWebAlertDoc({ _id: "507f1f77bcf86cd799439011" }));
    mockCctvAlertModel.findByIdAndDelete.mockResolvedValueOnce(createCctvAlertDoc({
      _id: "507f1f77bcf86cd799439012",
      sos_img: "cctv_sos_delete.jpg",
    }));

    const deletedWeb = await request(app)
      .delete("/api/v1/admin/management/alerts/web/507f1f77bcf86cd799439011")
      .set("Authorization", "Bearer admin-token");

    expect(deletedWeb.status).toBe(200);
    expect(deletedWeb.body.data.kind).toBe("web");

    const deletedCctv = await request(app)
      .delete("/api/v1/admin/management/alerts/cctv/507f1f77bcf86cd799439012")
      .set("Authorization", "Bearer admin-token");

    expect(deletedCctv.status).toBe(200);
    expect(deletedCctv.body.data.kind).toBe("cctv");
    expect(mockRemoveCCTVImage).toHaveBeenCalledWith("cctv_sos_delete.jpg");
  });

  it("creates, lists, and resolves a web SOS alert", async () => {
    mockWebAlertModel.create.mockResolvedValueOnce(createWebAlertDoc({ _id: "web-alert-2" }));
    mockWebAlertModel.find.mockReturnValueOnce(createListQuery([createWebAlertDoc({ _id: "web-alert-2" })]));
    mockWebAlertModel.findByIdAndUpdate.mockResolvedValueOnce(createWebAlertDoc({
      _id: "web-alert-2",
      status: "resolved",
    }));

    const createAlert = await request(app)
      .post("/api/v1/sos")
      .set("Authorization", "Bearer user-token")
      .send({ longitude: 77.1, latitude: 28.6, accuracy: 14 });

    expect(createAlert.status).toBe(201);
    expect(createAlert.body.data.alertId).toBe("web-alert-2");
    expect(mockBroadcastNewAlert).toHaveBeenCalled();

    const activeAlerts = await request(app)
      .get("/api/v1/sos/active")
      .query({ page: 1, limit: 20 })
      .set("Authorization", "Bearer admin-token");

    expect(activeAlerts.status).toBe(200);
    expect(activeAlerts.body.data.alerts).toHaveLength(1);

    const resolveAlert = await request(app)
      .put("/api/v1/sos/set-sos-resolved/507f1f77bcf86cd799439013")
      .set("Authorization", "Bearer admin-token");

    expect(resolveAlert.status).toBe(200);
    expect(resolveAlert.body.message).toBe("Web SOS alert marked as resolved");
  });

  it("creates, lists, and resolves a CCTV SOS alert", async () => {
    mockBuildCCTVAlertDocument.mockImplementationOnce(({ body, savedFileName }) => createCctvAlertDoc({
      _id: "cctv-alert-2",
      sos_img: savedFileName,
      eventId: body.eventId || "event-002",
      location: { type: "Point", coordinates: [Number(body.longitude), Number(body.latitude)] },
    }));
    mockCctvAlertModel.create.mockResolvedValueOnce(createCctvAlertDoc({ _id: "cctv-alert-2" }));
    mockCctvAlertModel.find.mockReturnValueOnce(createListQuery([createCctvAlertDoc({ _id: "cctv-alert-2" })]));
    mockCctvAlertModel.findByIdAndUpdate.mockResolvedValueOnce(createCctvAlertDoc({
      _id: "cctv-alert-2",
      status: "resolved",
    }));

    const createAlert = await request(app)
      .post("/api/v1/cctv/internal")
      .send({ longitude: 77.3, latitude: 28.8, source: "CCTV", eventId: "event-002" });

    expect(createAlert.status).toBe(201);
    expect(createAlert.body.data.alertId).toBe("cctv-alert-2");

    const activeAlerts = await request(app)
      .get("/api/v1/cctv/active")
      .set("Authorization", "Bearer admin-token");

    expect(activeAlerts.status).toBe(200);
    expect(activeAlerts.body.data.alerts).toHaveLength(1);

    const allAlerts = await request(app)
      .get("/api/v1/cctv/all-alerts")
      .set("Authorization", "Bearer admin-token");

    expect(allAlerts.status).toBe(200);
    expect(allAlerts.body.data.alerts).toHaveLength(1);

    const resolveAlert = await request(app)
      .put("/api/v1/cctv/set-sos-resolved/507f1f77bcf86cd799439014")
      .set("Authorization", "Bearer admin-token");

    expect(resolveAlert.status).toBe(200);
    expect(resolveAlert.body.message).toBe("CCTV SOS alert marked as resolved");
  });
});
import mongoose from "mongoose";
import { Admin } from "../models/admin.model.js";
import { User } from "../models/user.model.js";
import { SOSAlert } from "../models/websos.model.js";
import { CCTVSOSAlert } from "../models/cctvsos.model.js";
import { ApiError } from "../utils/ApiError.js";
import { ApiResponse } from "../utils/ApiResponse.js";
import { asyncHandler } from "../utils/asyncHandler.js";
import { logSecurityEvent } from "../utils/logger.js";

const parsePagination = (query) => {
  const page = Math.max(1, parseInt(query.page, 10) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(query.limit, 10) || 12));
  const skip = (page - 1) * limit;
  return { page, limit, skip };
};

const getStatusFilter = (status) => {
  if (status === "active") return { isActive: true };
  if (status === "inactive") return { isActive: false };
  return {};
};

const normalizeMedicalConditions = (value) => {
  if (value === undefined) return undefined;

  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }

  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return [];
};

export const getManagementOverview = asyncHandler(async (req, res) => {
  const [
    totalUsers,
    activeUsers,
    totalAdmins,
    activeAdmins,
    totalWebAlerts,
    activeWebAlerts,
    totalCCTVAlerts,
    activeCCTVAlerts,
  ] = await Promise.all([
    User.countDocuments({}),
    User.countDocuments({ isActive: true }),
    Admin.countDocuments({}),
    Admin.countDocuments({ isActive: true }),
    SOSAlert.countDocuments({}),
    SOSAlert.countDocuments({ status: "active" }),
    CCTVSOSAlert.countDocuments({}),
    CCTVSOSAlert.countDocuments({ status: "active" }),
  ]);

  return res.status(200).json(
    new ApiResponse(200, {
      users: {
        total: totalUsers,
        active: activeUsers,
        inactive: totalUsers - activeUsers,
      },
      admins: {
        total: totalAdmins,
        active: activeAdmins,
        inactive: totalAdmins - activeAdmins,
      },
      alerts: {
        web: {
          total: totalWebAlerts,
          active: activeWebAlerts,
          resolved: totalWebAlerts - activeWebAlerts,
        },
        cctv: {
          total: totalCCTVAlerts,
          active: activeCCTVAlerts,
          resolved: totalCCTVAlerts - activeCCTVAlerts,
        },
      },
    }, "Management overview fetched successfully")
  );
});

export const getManagedUsers = asyncHandler(async (req, res) => {
  const { page, limit, skip } = parsePagination(req.query);
  const search = (req.query.search || "").trim();
  const status = (req.query.status || "all").trim().toLowerCase();

  const statusFilter = getStatusFilter(status);
  const filter = {
    ...statusFilter,
    ...(search
      ? {
          $or: [
            { fullName: { $regex: search, $options: "i" } },
            { username: { $regex: search, $options: "i" } },
            { email: { $regex: search, $options: "i" } },
            { contact: { $regex: search, $options: "i" } },
            { emergencyEmail: { $regex: search, $options: "i" } },
            { address: { $regex: search, $options: "i" } },
            { city: { $regex: search, $options: "i" } },
            { state: { $regex: search, $options: "i" } },
            { pincode: { $regex: search, $options: "i" } },
          ],
        }
      : {}),
  };

  const [users, total] = await Promise.all([
    User.find(filter)
      .select(
        "fullName username email avatar contact age bloodGroup medicalInfo medicalConditions allergies emergencyContact1 emergencyContact2 emergencyEmail address city state pincode shareMedicalInfo shareLocation isActive createdAt updatedAt"
      )
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    User.countDocuments(filter),
  ]);

  return res.status(200).json(
    new ApiResponse(200, {
      users,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit),
      },
      filters: { search, status },
    }, "Managed users fetched successfully")
  );
});

export const updateManagedUser = asyncHandler(async (req, res) => {
  const { userId } = req.params;
  const {
    fullName,
    username,
    email,
    contact,
    age,
    bloodGroup,
    medicalInfo,
    medicalConditions,
    allergies,
    city,
    state,
    pincode,
    address,
    emergencyContact1,
    emergencyContact2,
    emergencyEmail,
    shareMedicalInfo,
    shareLocation,
    password,
    isActive,
  } = req.body;

  const user = await User.findById(userId);
  if (!user) {
    throw new ApiError(404, "User not found");
  }

  if (username && username.toLowerCase() !== user.username) {
    const usernameExists = await User.findOne({ username: username.toLowerCase(), _id: { $ne: user._id } });
    if (usernameExists) {
      throw new ApiError(409, "Username already in use");
    }
    user.username = username.toLowerCase();
  }

  if (email && email.toLowerCase() !== user.email) {
    const emailExists = await User.findOne({ email: email.toLowerCase(), _id: { $ne: user._id } });
    if (emailExists) {
      throw new ApiError(409, "Email already in use");
    }
    user.email = email.toLowerCase();
  }

  if (fullName !== undefined) user.fullName = fullName;
  if (contact !== undefined) user.contact = contact;
  if (age !== undefined) user.age = age;
  if (bloodGroup !== undefined) user.bloodGroup = bloodGroup;
  if (medicalInfo !== undefined) user.medicalInfo = medicalInfo;

  const normalizedMedicalConditions = normalizeMedicalConditions(medicalConditions);
  if (normalizedMedicalConditions !== undefined) {
    user.medicalConditions = normalizedMedicalConditions;
  }

  if (allergies !== undefined) user.allergies = allergies;
  if (city !== undefined) user.city = city;
  if (state !== undefined) user.state = state;
  if (pincode !== undefined) user.pincode = pincode;
  if (address !== undefined) user.address = address;
  if (emergencyContact1 !== undefined) user.emergencyContact1 = emergencyContact1;
  if (emergencyContact2 !== undefined) user.emergencyContact2 = emergencyContact2;
  if (emergencyEmail !== undefined) {
    user.emergencyEmail = emergencyEmail ? emergencyEmail.toLowerCase() : "";
  }
  if (shareMedicalInfo !== undefined) user.shareMedicalInfo = shareMedicalInfo;
  if (shareLocation !== undefined) user.shareLocation = shareLocation;
  if (password) user.password = password;

  if (req.file?.filename) {
    user.avatar = `/user_imgs/${req.file.filename}`;
  }

  if (isActive !== undefined) {
    user.isActive = isActive;
    if (!isActive) {
      user.refreshToken = undefined;
    }
  }

  await user.save({ validateBeforeSave: false });

  const safeUser = await User.findById(user._id).select(
    "fullName username email avatar contact age bloodGroup medicalInfo medicalConditions allergies emergencyContact1 emergencyContact2 emergencyEmail address city state pincode shareMedicalInfo shareLocation isActive createdAt updatedAt"
  );

  logSecurityEvent("MANAGED_USER_UPDATED", {
    byAdminId: req.admin._id,
    userId: user._id,
    isActive: safeUser.isActive,
    ip: req.ip,
  });

  return res.status(200).json(new ApiResponse(200, safeUser, "User updated successfully"));
});

export const toggleManagedUserStatus = asyncHandler(async (req, res) => {
  const { userId } = req.params;
  const { isActive } = req.body;

  const update = {
    isActive,
    ...(isActive ? {} : { $unset: { refreshToken: 1 } }),
  };

  const user = await User.findByIdAndUpdate(userId, update, { new: true })
    .select("fullName username email isActive updatedAt");

  if (!user) {
    throw new ApiError(404, "User not found");
  }

  logSecurityEvent("MANAGED_USER_STATUS_CHANGED", {
    byAdminId: req.admin._id,
    userId: user._id,
    isActive: user.isActive,
    ip: req.ip,
  });

  return res.status(200).json(
    new ApiResponse(200, user, `User ${isActive ? "activated" : "deactivated"} successfully`)
  );
});

export const getManagedAdmins = asyncHandler(async (req, res) => {
  const { page, limit, skip } = parsePagination(req.query);
  const search = (req.query.search || "").trim();
  const status = (req.query.status || "all").trim().toLowerCase();

  const statusFilter = getStatusFilter(status);
  const filter = {
    ...statusFilter,
    ...(search
      ? {
          $or: [
            { officerName: { $regex: search, $options: "i" } },
            { email: { $regex: search, $options: "i" } },
            { policeStation: { $regex: search, $options: "i" } },
          ],
        }
      : {}),
  };

  const [admins, total] = await Promise.all([
    Admin.find(filter)
      .select("officerName email policeStation officersInStation isActive createdAt updatedAt")
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit),
    Admin.countDocuments(filter),
  ]);

  const enrichedAdmins = admins.map((adminDoc) => {
    const adminData = adminDoc.toObject();
    return {
      ...adminData,
      isCurrent: adminData._id.toString() === req.admin._id.toString(),
    };
  });

  return res.status(200).json(
    new ApiResponse(200, {
      admins: enrichedAdmins,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit),
      },
      filters: { search, status },
    }, "Managed admins fetched successfully")
  );
});

export const createManagedAdmin = asyncHandler(async (req, res) => {
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

  const sanitized = await Admin.findById(newAdmin._id).select(
    "officerName email policeStation officersInStation isActive createdAt updatedAt"
  );

  logSecurityEvent("MANAGED_ADMIN_CREATED", {
    byAdminId: req.admin._id,
    adminId: newAdmin._id,
    email: newAdmin.email,
    policeStation: newAdmin.policeStation,
    ip: req.ip,
  });

  return res.status(201).json(new ApiResponse(201, sanitized, "Admin created successfully"));
});

export const updateManagedAdmin = asyncHandler(async (req, res) => {
  const { adminId } = req.params;
  const { officerName, email, policeStation, officersInStation, password, isActive } = req.body;

  const admin = await Admin.findById(adminId);
  if (!admin) {
    throw new ApiError(404, "Admin not found");
  }

  const isSelf = admin._id.toString() === req.admin._id.toString();

  if (email && email.toLowerCase() !== admin.email) {
    const emailExists = await Admin.findOne({ email: email.toLowerCase(), _id: { $ne: admin._id } });
    if (emailExists) {
      throw new ApiError(409, "Email already in use");
    }
    admin.email = email.toLowerCase();
  }

  if (policeStation && policeStation !== admin.policeStation) {
    const stationExists = await Admin.findOne({ policeStation, _id: { $ne: admin._id } });
    if (stationExists) {
      throw new ApiError(409, "Police station already assigned to another admin");
    }
    admin.policeStation = policeStation;
  }

  if (officerName !== undefined) admin.officerName = officerName;
  if (officersInStation !== undefined) admin.officersInStation = officersInStation;
  if (password) admin.password = password;

  if (isActive !== undefined) {
    if (!isActive && isSelf) {
      throw new ApiError(400, "You cannot deactivate your own account");
    }
    admin.isActive = isActive;
    if (!isActive) {
      admin.refreshToken = undefined;
    }
  }

  await admin.save({ validateBeforeSave: false });

  const safeAdmin = await Admin.findById(admin._id).select(
    "officerName email policeStation officersInStation isActive createdAt updatedAt"
  );

  logSecurityEvent("MANAGED_ADMIN_UPDATED", {
    byAdminId: req.admin._id,
    targetAdminId: admin._id,
    isActive: safeAdmin.isActive,
    ip: req.ip,
  });

  return res.status(200).json(new ApiResponse(200, safeAdmin, "Admin updated successfully"));
});

export const toggleManagedAdminStatus = asyncHandler(async (req, res) => {
  const { adminId } = req.params;
  const { isActive } = req.body;

  if (!mongoose.Types.ObjectId.isValid(adminId)) {
    throw new ApiError(400, "Invalid adminId format");
  }

  if (!isActive && adminId.toString() === req.admin._id.toString()) {
    throw new ApiError(400, "You cannot deactivate your own account");
  }

  const update = {
    isActive,
    ...(isActive ? {} : { $unset: { refreshToken: 1 } }),
  };

  const admin = await Admin.findByIdAndUpdate(adminId, update, { new: true })
    .select("officerName email policeStation isActive updatedAt");

  if (!admin) {
    throw new ApiError(404, "Admin not found");
  }

  logSecurityEvent("MANAGED_ADMIN_STATUS_CHANGED", {
    byAdminId: req.admin._id,
    targetAdminId: admin._id,
    isActive: admin.isActive,
    ip: req.ip,
  });

  return res.status(200).json(
    new ApiResponse(200, admin, `Admin ${isActive ? "activated" : "deactivated"} successfully`)
  );
});

import mongoose, { Schema } from "mongoose";
import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";

const userSchema = new Schema(
  {
    username: { type: String, required: true, unique: true, trim: true, index: true },
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
      index: true,
    },
    fullName: { type: String, required: true, trim: true, index: true },
    avatar: { type: String, required: true },
    contact: { type: String, required: true, trim: true },
    age: { type: Number, required: true, min: 13, max: 120 },
    password: { type: String, required: true },
    isActive: { type: Boolean, default: true, index: true },
    refreshToken: String,
    
    // Medical & Emergency Information
    bloodGroup: { 
      type: String, 
      enum: ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', ''], 
      default: '' 
    },
    medicalInfo: { type: String, trim: true, default: '' },
    medicalConditions: [{ type: String, trim: true }],
    allergies: { type: String, trim: true, default: '' },
    
    // Emergency Contacts
    emergencyContact1: { type: String, trim: true, default: '' },
    emergencyContact2: { type: String, trim: true, default: '' },
    emergencyEmail: { type: String, trim: true, lowercase: true, default: '' },
    
    // Address Information
    address: { type: String, trim: true, default: '' },
    city: { type: String, trim: true, default: '' },
    state: { type: String, trim: true, default: '' },
    pincode: { type: String, trim: true, default: '' },
    
    // Settings
    shareMedicalInfo: { type: Boolean, default: true },
    shareLocation: { type: Boolean, default: true },
  },
  { timestamps: true }
);

userSchema.pre("save", async function (next) {
  if (!this.isModified("password")) return next();
  this.password = await bcrypt.hash(this.password, 10);
  next();
});

userSchema.methods.isPasswordCorrect = function (password) {
  return bcrypt.compare(password, this.password);
};

userSchema.methods.generateAccessToken = function () {
  return jwt.sign(
    {
      _id: this._id,
      email: this.email,
      username: this.username,
      fullName: this.fullName,
    },
    process.env.ACCESS_TOKEN_SECRET,
    { expiresIn: process.env.ACCESS_TOKEN_EXPIRY }
  );
};

userSchema.methods.generateRefreshToken = function () {
  return jwt.sign(
    { _id: this._id },
    process.env.REFRESH_TOKEN_SECRET,
    { expiresIn: process.env.REFRESH_TOKEN_EXPIRY }
  );
};

export const User = mongoose.model("User", userSchema);

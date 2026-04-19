import mongoose from "mongoose";

const webSosAlertSchema = new mongoose.Schema(
  {
    userId: { type: mongoose.Schema.Types.ObjectId, ref: "User", required: true },
    location: {
      type: { type: String, default: "Point", enum: ["Point"] },
      coordinates: { type: [Number], required: true },
      accuracy: Number,
    },
    // Live location address (geocoded from coordinates when alert is created)
    liveAddress: { type: String, default: "" },
    status: { type: String, enum: ["active", "resolved"], default: "active" },
    resolvedAt: { type: Date, default: null },
    resolvedBy: { type: mongoose.Schema.Types.ObjectId, ref: "Admin", default: null },
  },
  { timestamps: true }
);

webSosAlertSchema.index({ location: "2dsphere" });
webSosAlertSchema.index({ status: 1, createdAt: -1 });
webSosAlertSchema.index({ userId: 1, status: 1, createdAt: -1 });
export const SOSAlert = mongoose.model("web_sos_alert", webSosAlertSchema);

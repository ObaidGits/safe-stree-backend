import mongoose from "mongoose";

const cctvSosAlertSchema = new mongoose.Schema(
  {
    location: {
      type: { type: String, default: "Point", enum: ["Point"] },
      coordinates: { type: [Number], required: true },
      accuracy: Number,
    },
    status: { type: String, enum: ["active", "resolved"], default: "active" },
    sos_img: { type: String, required: true },
    resolvedAt: { type: Date, default: null },
    resolvedBy: { type: mongoose.Schema.Types.ObjectId, ref: "Admin", default: null },
  },
  { timestamps: true }
);

cctvSosAlertSchema.index({ location: "2dsphere" });
cctvSosAlertSchema.index({ status: 1, createdAt: -1 });
export const CCTVSOSAlert = mongoose.model("cctv_sos_alert", cctvSosAlertSchema);

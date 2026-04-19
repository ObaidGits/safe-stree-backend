import multer from "multer";
import path from "path";
import fs from "fs";

const folderPath = path.resolve("public/cctv_sos");
if (!fs.existsSync(folderPath)) fs.mkdirSync(folderPath, { recursive: true });

const storage = multer.diskStorage({
  destination: (_, __, cb) => cb(null, folderPath),
  filename: (req, file, cb) => {
    const unique = `${Date.now()}-${Math.round(Math.random() * 1e9)}`;
    const ext = path.extname(file.originalname);
    const name = `cctv_sos_${unique}${ext}`;
    req.savedFileName = name;
    cb(null, name);
  },
});

const fileFilter = (req, file, cb) => {
  const allowedMimes = new Set(["image/jpeg", "image/png", "image/webp"]);
  if (!allowedMimes.has(file.mimetype)) {
    return cb(new Error("Only JPEG, PNG, and WebP image uploads are allowed"), false);
  }
  cb(null, true);
};

export const uploadCCTVSOS = multer({
  storage,
  fileFilter,
  limits: { fileSize: 10 * 1024 * 1024 }, // 10 MB
});

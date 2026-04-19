import multer from "multer";
import path from "path";
import fs from "fs";

const uploadPath = path.resolve("public/user_imgs");
if (!fs.existsSync(uploadPath)) fs.mkdirSync(uploadPath, { recursive: true });

const storage = multer.diskStorage({
  destination: (_, __, cb) => cb(null, uploadPath),
  filename: (_, file, cb) => {
    const unique = `${Date.now()}-${Math.round(Math.random() * 1e9)}`;
    const ext = path.extname(file.originalname);
    cb(null, `user-${unique}${ext}`);
  },
});

const fileFilter = (req, file, cb) => {
  const allowedMimes = new Set(["image/jpeg", "image/png", "image/webp"]);
  if (!allowedMimes.has(file.mimetype)) {
    return cb(new Error("Only JPEG, PNG, and WebP image files are allowed"), false);
  }
  cb(null, true);
};

export const userMulter = multer({
  storage,
  fileFilter,
  limits: { fileSize: 8 * 1024 * 1024 },
});

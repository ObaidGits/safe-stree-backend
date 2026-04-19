import multer from "multer";
import path from "path";
import fs from "fs";

const tempPath = path.resolve("public/temp");
if (!fs.existsSync(tempPath)) fs.mkdirSync(tempPath, { recursive: true });

const storage = multer.diskStorage({
  destination: (_, __, cb) => cb(null, tempPath),
  filename: (_, file, cb) => {
    const unique = `${Date.now()}-${Math.round(Math.random() * 1e9)}`;
    cb(null, `${unique}-${file.originalname}`);
  },
});

export const upload = multer({
  storage,
  limits: { fileSize: 10 * 1024 * 1024 },
});

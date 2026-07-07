import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";
import connectDB from "../db/index.js";
import { User } from "../models/user.model.js";
import { Admin } from "../models/admin.model.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

const envCandidates = [
  path.resolve(process.cwd(), ".env"),
  path.resolve(projectRoot, ".env"),
];

for (const envPath of envCandidates) {
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath });
    break;
  }
}

const credsFilePath = path.resolve(projectRoot, "creds.txt");

const demoUser = {
  username: "rashi_sharma",
  email: "rashi.sharma@safestree.local",
  fullName: "Rashi Sharma",
  avatar: "/user_imgs/user-1766345138750_939620101_chinese_girl_summer_hat_scc7dxbtxfo20fh6.jpg",
  contact: "+919876543210",
  age: 24,
  password: "User@1234",
  bloodGroup: "O+",
  medicalInfo: "No known chronic condition. Seasonal allergy to dust.",
  medicalConditions: ["Seasonal allergy"],
  allergies: "Dust",
  emergencyContact1: "+919812345678",
  emergencyContact2: "+919876123456",
  emergencyEmail: "meera.sharma@example.com",
  address: "24 Lake View Residency, Sector 12",
  city: "Jaipur",
  state: "Rajasthan",
  pincode: "302017",
  shareMedicalInfo: true,
  shareLocation: true,
};

const demoAdmin = {
  officerName: "Inspector Priya Verma",
  email: "priya.verma@safestree.local",
  policeStation: "Civil Lines Police Station",
  password: "Admin@1234",
  officersInStation: [
    {
      name: "Inspector Priya Verma",
      rank: "Inspector",
      contact: "+919811223344",
      badgeId: "ST-OPS-001",
    },
    {
      name: "Constable Anil Mehta",
      rank: "Constable",
      contact: "+919988776655",
      badgeId: "ST-OPS-002",
    },
  ],
};

const removeMatchingRecords = async () => {
  await Promise.all([
    User.deleteOne({
      $or: [
        { username: demoUser.username },
        { email: demoUser.email },
      ],
    }),
    Admin.deleteOne({
      $or: [
        { email: demoAdmin.email },
        { policeStation: demoAdmin.policeStation },
      ],
    }),
  ]);
};

const writeCredsFile = (user, admin) => {
  const contents = [
    "SafeStree Dev Credentials",
    `Generated At: ${new Date().toISOString()}`,
    "",
    "USER",
    `Full Name: ${user.fullName}`,
    `Username: ${user.username}`,
    `Email: ${user.email}`,
    `Password: ${user.password}`,
    "",
    "ADMIN",
    `Officer Name: ${admin.officerName}`,
    `Email: ${admin.email}`,
    `Password: ${admin.password}`,
    `Police Station: ${admin.policeStation}`,
    "",
  ].join("\n");

  fs.writeFileSync(credsFilePath, contents, {
    encoding: "utf8",
    mode: 0o600,
  });
};

const seed = async () => {
  await connectDB();

  await removeMatchingRecords();

  const createdUser = await User.create(demoUser);
  const createdAdmin = await Admin.create(demoAdmin);

  writeCredsFile(demoUser, demoAdmin);

  console.log("Seed complete.");
  console.log(`User: ${createdUser.username} / ${demoUser.password}`);
  console.log(`Admin: ${createdAdmin.email} / ${demoAdmin.password}`);
  console.log(`Credentials file: ${credsFilePath}`);

  process.exit(0);
};

seed().catch((error) => {
  console.error("Seed failed:", error);
  process.exit(1);
});

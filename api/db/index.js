import mongoose from "mongoose";
import dns from "dns";

// Fix DNS resolution issues by using Google DNS
dns.setServers(["8.8.8.8", "8.8.4.4"]);

const connectDB = async () => {
  try {
    const baseUri = process.env.MONGODB_URI;
    const dbName = process.env.DB_NAME;

    if (!baseUri) {
      console.error("❌ MONGODB_URI missing");
      process.exit(1);
    }

    const finalUri = baseUri.includes("/")
      ? baseUri
      : `${baseUri}/${dbName}`;

    const connectionInstance = await mongoose.connect(finalUri, {
      autoIndex: true,
      serverSelectionTimeoutMS: 10000,
      family: 4,  // Force IPv4
    });

    console.log(
      `\n✅ MongoDB Connected → ${connectionInstance.connection.host}/${connectionInstance.connection.name}`
    );
  } catch (error) {
    console.error("❌ MongoDB connection error:", error.message);
    process.exit(1);
  }
};

export default connectDB;

import { Server } from "socket.io";
import jwt from "jsonwebtoken";

let io = null;
const userSocketMap = new Map(); // userId -> socketId
const onlineUsers = new Set(); // Set of online userIds
const roomParticipants = new Map(); // roomId -> Set of { socketId, role }

/**
 * Initialize Socket.IO server with authentication
 * @param {import("http").Server} httpServer - HTTP server instance
 * @param {string[]} allowedOrigins - CORS allowed origins
 */
export const initializeSocket = (httpServer, allowedOrigins) => {
  io = new Server(httpServer, {
    cors: {
      origin: allowedOrigins.length ? allowedOrigins : true,
      methods: ["GET", "POST"],
      credentials: true,
    },
    pingTimeout: 60000,
    pingInterval: 25000,
  });

  // Socket authentication middleware
  io.use((socket, next) => {
    const token = socket.handshake.auth?.token || socket.handshake.headers?.authorization?.split(" ")[1];
    
    // Allow connection but mark as unauthenticated
    if (!token) {
      socket.authenticated = false;
      socket.userId = null;
      socket.isAdmin = false;
      return next();
    }

    try {
      const decoded = jwt.verify(token, process.env.ACCESS_TOKEN_SECRET);
      socket.authenticated = true;
      socket.userId = decoded._id;
      socket.isAdmin = !!decoded.officerName;
      console.log(`🔐 Socket authenticated: userId=${decoded._id}, isAdmin=${!!decoded.officerName}`);
      next();
    } catch (err) {
      console.log(`⚠️ Token verification failed: ${err.message}`);
      socket.authenticated = false;
      socket.userId = null;
      socket.isAdmin = false;
      next();
    }
  });

  io.on("connection", (socket) => {
    console.log(`🔌 Socket connected: ${socket.id} (Auth: ${socket.authenticated}, Admin: ${socket.isAdmin})`);

    const emitSocketError = (event, message, code = "UNAUTHORIZED") => {
      socket.emit(event, { error: message, code });
    };

    const safeOn = (event, handler) => {
      socket.on(event, (payload = {}) => {
        try {
          handler(payload);
        } catch (err) {
          console.error(`Socket error on ${event}:`, err.message);
        }
      });
    };

    // ==================== USER REGISTRATION ====================

    // Register user for targeted notifications
    safeOn("register_user", ({ userId }) => {
      if (!socket.authenticated || !socket.userId) {
        emitSocketError("registration_error", "Authentication required", "AUTH_REQUIRED");
        return;
      }

      if (!userId) {
        console.log(`⚠️ register_user called without userId`);
        return;
      }

      if (String(userId) !== String(socket.userId)) {
        console.log(`⚠️ register_user mismatch: payload=${userId}, token=${socket.userId}`);
        emitSocketError("registration_error", "User identity mismatch", "IDENTITY_MISMATCH");
        return;
      }
      
      // Store mapping and add to online users
      userSocketMap.set(socket.userId, socket.id);
      onlineUsers.add(socket.userId);
      socket.join(socket.userId);
      
      console.log(`📱 User ${socket.userId} registered on socket ${socket.id}`);
      console.log(`📊 Online users: ${onlineUsers.size}`);
      
      // Confirm registration to client
      socket.emit("registration_confirmed", { userId: socket.userId, socketId: socket.id });
      
      // Broadcast user online status (for admin panels)
      io.emit("user_online_status", { userId: socket.userId, online: true });
    });

    // Check if a user is online
    safeOn("check_user_online", ({ userId }) => {
      if (!socket.authenticated || !socket.userId) {
        emitSocketError("socket_error", "Authentication required", "AUTH_REQUIRED");
        return;
      }

      if (!socket.isAdmin && String(userId) !== String(socket.userId)) {
        emitSocketError("socket_error", "Access denied", "FORBIDDEN");
        return;
      }

      const isOnline = onlineUsers.has(userId);
      const targetSocketId = userSocketMap.get(userId);
      
      console.log(`🔍 Checking if user ${userId} is online: ${isOnline}`);
      
      socket.emit("user_online_status", { 
        userId, 
        online: isOnline,
        socketId: targetSocketId || null
      });
    });

    // ==================== LIVE STREAMING EVENTS ====================

    // Admin requests live video from user
    safeOn("request_live_video", ({ targetUserId }) => {
      if (!socket.authenticated || !socket.userId || !socket.isAdmin) {
        emitSocketError("live_stream_error", "Admin authentication required", "FORBIDDEN");
        return;
      }

      console.log(`📹 request_live_video from socket ${socket.id}:`, {
        targetUserId,
        authenticated: socket.authenticated,
        isAdmin: socket.isAdmin
      });
      
      // Validate targetUserId
      if (!targetUserId || targetUserId === 'undefined') {
        console.log(`❌ Invalid targetUserId: ${targetUserId}`);
        socket.emit("live_stream_error", { 
          error: "Invalid user ID",
          code: "INVALID_USER_ID"
        });
        return;
      }
      
      // Check if target user is online
      const isOnline = onlineUsers.has(targetUserId);
      const targetSocketId = userSocketMap.get(targetUserId);
      
      if (!isOnline || !targetSocketId) {
        console.log(`📵 User ${targetUserId} is not online`);
        socket.emit("user_offline", { 
          userId: targetUserId,
          message: "User is not currently online"
        });
        return;
      }
      
      console.log(`📹 Sending live video request to user ${targetUserId} (socket: ${targetSocketId})`);
      
      // Send request to the target user
      io.to(targetSocketId).emit("request_live_video", { 
        targetUserId,
        requesterId: socket.id 
      });
      
      // Also emit to the room (backup)
      io.to(targetUserId).emit("request_live_video", { 
        targetUserId,
        requesterId: socket.id 
      });
      
      // Confirm to admin that request was sent
      socket.emit("live_request_sent", { 
        targetUserId,
        message: "Request sent to user" 
      });
    });

    // Join a WebRTC room
    safeOn("join-room", ({ roomId, role }) => {
      if (!socket.authenticated || !socket.userId) {
        emitSocketError("live_stream_error", "Authentication required", "AUTH_REQUIRED");
        return;
      }

      if (!roomId || roomId === 'undefined') {
        console.log(`❌ Invalid roomId for join-room: ${roomId}`);
        return;
      }

      if (role !== "admin" && role !== "user") {
        emitSocketError("live_stream_error", "Invalid room role", "INVALID_ROLE");
        return;
      }

      if (role === "admin" && !socket.isAdmin) {
        emitSocketError("live_stream_error", "Admin access required", "FORBIDDEN");
        return;
      }

      if (role === "user" && String(roomId) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "Room identity mismatch", "IDENTITY_MISMATCH");
        return;
      }
      
      socket.join(roomId);
      
      // Track participants
      if (!roomParticipants.has(roomId)) {
        roomParticipants.set(roomId, new Set());
      }
      roomParticipants.get(roomId).add({ socketId: socket.id, role });
      
      console.log(`🚪 ${role} joined room: ${roomId}`);
      
      // Notify other participants
      socket.to(roomId).emit("user-joined", { role, socketId: socket.id });
      
      // If admin joined, notify user they can start streaming
      if (role === "admin") {
        socket.to(roomId).emit("admin_ready", { roomId });
      }
    });

    // WebRTC offer from user
    safeOn("offer", ({ roomId, offer }) => {
      if (!socket.authenticated || !socket.userId) {
        emitSocketError("live_stream_error", "Authentication required", "AUTH_REQUIRED");
        return;
      }

      if (!roomId || !offer) {
        console.log(`❌ Invalid offer: roomId=${roomId}, offer=${!!offer}`);
        return;
      }

      if (!socket.rooms.has(roomId)) {
        emitSocketError("live_stream_error", "Join room before signaling", "ROOM_NOT_JOINED");
        return;
      }

      if (!socket.isAdmin && String(roomId) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "Room identity mismatch", "IDENTITY_MISMATCH");
        return;
      }

      const room = io.sockets.adapter.rooms.get(roomId);
      const roomSize = room ? room.size : 0;
      console.log(`📤 Offer relayed to room: ${roomId}, room size: ${roomSize}`);
      socket.to(roomId).emit("offer", offer);
    });

    // WebRTC answer from admin
    safeOn("answer", ({ roomId, answer }) => {
      if (!socket.authenticated || !socket.userId || !socket.isAdmin) {
        emitSocketError("live_stream_error", "Admin authentication required", "FORBIDDEN");
        return;
      }

      if (!roomId || !answer) {
        console.log(`❌ Invalid answer: roomId=${roomId}, answer=${!!answer}`);
        return;
      }

      if (!socket.rooms.has(roomId)) {
        emitSocketError("live_stream_error", "Join room before signaling", "ROOM_NOT_JOINED");
        return;
      }

      const room = io.sockets.adapter.rooms.get(roomId);
      const roomSize = room ? room.size : 0;
      console.log(`📥 Answer relayed to room: ${roomId}, room size: ${roomSize}`);
      socket.to(roomId).emit("answer", answer);
    });

    // ICE candidate exchange
    safeOn("ice-candidate", ({ roomId, candidate }) => {
      if (!socket.authenticated || !socket.userId) {
        emitSocketError("live_stream_error", "Authentication required", "AUTH_REQUIRED");
        return;
      }

      if (!roomId || !candidate) return;

      if (!socket.rooms.has(roomId)) {
        emitSocketError("live_stream_error", "Join room before signaling", "ROOM_NOT_JOINED");
        return;
      }

      if (!socket.isAdmin && String(roomId) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "Room identity mismatch", "IDENTITY_MISMATCH");
        return;
      }

      console.log(`🧊 ICE candidate relayed to room: ${roomId}, type: ${candidate.type || 'unknown'}`);
      socket.to(roomId).emit("ice-candidate", candidate);
    });

    // User accepted stream request
    safeOn("live_stream_accepted", ({ roomId, userId }) => {
      if (!socket.authenticated || !socket.userId || socket.isAdmin) {
        emitSocketError("live_stream_error", "User authentication required", "FORBIDDEN");
        return;
      }

      if (!userId || String(userId) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "User identity mismatch", "IDENTITY_MISMATCH");
        return;
      }

      const targetRoom = roomId || userId;

      if (String(targetRoom) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "Invalid room target", "INVALID_ROOM");
        return;
      }

      if (targetRoom) {
        console.log(`✅ User ${userId} accepted stream request`);
        io.to(targetRoom).emit("live_stream_accepted", { userId });
      }
    });

    // User rejected stream request
    safeOn("live_stream_rejected", ({ roomId, userId }) => {
      if (!socket.authenticated || !socket.userId || socket.isAdmin) {
        emitSocketError("live_stream_error", "User authentication required", "FORBIDDEN");
        return;
      }

      if (!userId || String(userId) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "User identity mismatch", "IDENTITY_MISMATCH");
        return;
      }

      const targetRoom = roomId || userId;

      if (String(targetRoom) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "Invalid room target", "INVALID_ROOM");
        return;
      }

      if (targetRoom) {
        console.log(`❌ User ${userId} rejected stream request`);
        io.to(targetRoom).emit("live_stream_rejected", { userId });
      }
    });

    // User stopped streaming
    safeOn("live_stream_stopped", ({ roomId, userId }) => {
      if (!socket.authenticated || !socket.userId || socket.isAdmin) {
        emitSocketError("live_stream_error", "User authentication required", "FORBIDDEN");
        return;
      }

      if (!userId || String(userId) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "User identity mismatch", "IDENTITY_MISMATCH");
        return;
      }

      const targetRoom = roomId || userId;

      if (String(targetRoom) !== String(socket.userId)) {
        emitSocketError("live_stream_error", "Invalid room target", "INVALID_ROOM");
        return;
      }

      if (targetRoom) {
        console.log(`⏹️ User ${userId} stopped streaming`);
        io.to(targetRoom).emit("live_stream_stopped", { userId });
        // Clean up room
        roomParticipants.delete(targetRoom);
      }
    });

    // Admin disconnected from viewing
    safeOn("admin_disconnected", ({ roomId }) => {
      if (!socket.authenticated || !socket.userId || !socket.isAdmin) {
        emitSocketError("live_stream_error", "Admin authentication required", "FORBIDDEN");
        return;
      }

      if (roomId && roomId !== 'undefined') {
        if (!socket.rooms.has(roomId)) {
          emitSocketError("live_stream_error", "Join room before disconnecting", "ROOM_NOT_JOINED");
          return;
        }

        console.log(`👋 Admin disconnected from room: ${roomId}`);
        socket.to(roomId).emit("admin_disconnected", { roomId });
        socket.leave(roomId);
      }
    });

    // ==================== DISCONNECT HANDLING ====================

    socket.on("disconnect", (reason) => {
      console.log(`🔌 Socket disconnected: ${socket.id} (reason: ${reason})`);
      
      // Find and remove user from online tracking
      let disconnectedUserId = null;
      for (const [userId, sId] of userSocketMap.entries()) {
        if (sId === socket.id) {
          disconnectedUserId = userId;
          userSocketMap.delete(userId);
          onlineUsers.delete(userId);
          console.log(`📴 User ${userId} went offline`);
          
          // Notify any rooms this user was in
          io.emit("user_online_status", { userId, online: false });
          
          // Notify any active streaming sessions
          io.emit("live_stream_user_disconnected", { 
            userId,
            reason: "User disconnected from server"
          });
          break;
        }
      }
      
      // Clean up room participants
      for (const [roomId, participants] of roomParticipants.entries()) {
        const participantArray = Array.from(participants);
        for (const p of participantArray) {
          if (p.socketId === socket.id) {
            participants.delete(p);
            
            // Notify room that participant left
            socket.to(roomId).emit("participant_left", { 
              socketId: socket.id, 
              role: p.role,
              roomId 
            });
            
            // If admin left, notify user
            if (p.role === "admin") {
              io.to(roomId).emit("admin_disconnected", { roomId });
            }
            
            // If user left, notify admin
            if (p.role === "user") {
              io.to(roomId).emit("live_stream_stopped", { 
                userId: roomId,
                reason: "User disconnected"
              });
            }
            break;
          }
        }
        if (participants.size === 0) {
          roomParticipants.delete(roomId);
        }
      }
      
      console.log(`📊 Remaining online users: ${onlineUsers.size}`);
    });
  });

  return io;
};

/**
 * Broadcast new SOS alert to all connected admin clients
 * @param {Object} alert - Alert data to broadcast
 */
export const broadcastNewAlert = (alert) => {
  if (io) {
    io.sockets.sockets.forEach((clientSocket) => {
      if (clientSocket.authenticated && clientSocket.isAdmin) {
        clientSocket.emit("new_alert", alert);
      }
    });
    console.log(`🚨 Alert broadcast: ${alert._id || "new"}`);
  } else {
    console.error("Socket.IO not initialized - cannot broadcast alert");
  }
};

/**
 * Send notification to specific user
 * @param {string} userId - Target user ID
 * @param {string} event - Event name
 * @param {Object} data - Data to send
 */
export const notifyUser = (userId, event, data) => {
  if (io) {
    io.to(userId).emit(event, data);
  }
};

/**
 * Check if a user is online
 * @param {string} userId - User ID to check
 * @returns {boolean}
 */
export const isUserOnline = (userId) => {
  return onlineUsers.has(userId);
};

/**
 * Get count of online users
 * @returns {number}
 */
export const getOnlineUserCount = () => {
  return onlineUsers.size;
};

export const getIO = () => io;

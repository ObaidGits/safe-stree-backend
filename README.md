<div align="center">

<img src="https://img.shields.io/badge/SafeStree-Women's%20Safety%20Platform-ff69b4?style=for-the-badge&logo=shield&logoColor=white" alt="SafeStree" />

# 🛡️ SafeStree — Backend

### *The server-side brain of the safety ecosystem*

[![Node.js](https://img.shields.io/badge/Node.js-18+-339933?style=flat-square&logo=node.js&logoColor=white)](https://nodejs.org)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-7-47A248?style=flat-square&logo=mongodb&logoColor=white)](https://mongodb.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-4.x-010101?style=flat-square&logo=socket.io)](https://socket.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)

**[🔗 Frontend Repo](https://github.com/ObaidGits/safe-stree-frontend)** &nbsp;|&nbsp;
**[🔗 Unified Repo](https://github.com/ObaidGits/safe-stree-unified)** &nbsp;|&nbsp;
**[📖 Full Docs](https://github.com/ObaidGits/safe-stree-unified#readme)**

</div>

---

## 📌 What Is This?

This is the **backend** of SafeStree — a full-stack women's safety platform. This workspace contains **two services** that power everything server-side:

- 🟢 **`/api`** — Node.js + Express REST API with Socket.IO for real-time alert broadcasting, JWT authentication, and MongoDB persistence
- 🐍 **`/ml`** — Python 3.12 edge runtime that detects SOS gestures via camera (OpenCV + MediaPipe) and distress voice commands (Vosk), then submits automated CCTV alerts to the API

Together they form the complete emergency response backend — from user login to live alert delivery on admin dashboards.

---

## ✨ What It Does

| Capability | Description |
|---|---|
| 🔐 **Authentication** | JWT + httpOnly cookies, refresh tokens, bcrypt password hashing |
| 🆘 **SOS Alert Pipeline** | Receives, validates, persists, and broadcasts emergency alerts in real time |
| 📡 **Real-Time Broadcasting** | Socket.IO emits `new_alert` events to authenticated admin clients instantly |
| 🤚 **Gesture Detection** | ML service detects SOS hand gestures from camera using OpenCV + MediaPipe |
| 🎤 **Voice Detection** | Offline speech recognition using Vosk + fuzzy phrase matching |
| 🗺️ **Geospatial Enrichment** | Reverse geocoding via OpenCage; alerts stored with 2dsphere index |
| 📹 **WebRTC Signaling** | Socket.IO coordinates peer-to-peer live video between user and admin |
| 🏛️ **Admin Management** | Role-protected endpoints for incident management, user admin, and analytics |
| 📸 **Media Storage** | Saves CCTV snapshots, user avatars; serves via static routes |
| 📋 **Audit Logging** | Winston structured logging for all security events and API errors |
| 🛡️ **Security** | Rate limiting, NoSQL injection prevention, Helmet headers, CORS control |

---

## 🔧 Tech Stack

### API Service (`/api`) — Node.js

| Technology | Version | Purpose |
|---|---|---|
| **Node.js** | 18+ | JavaScript runtime |
| **Express.js** | 4.x | REST API framework |
| **MongoDB + Mongoose** | 7 / 8.x | Database and ODM |
| **Socket.IO** | 4.x | Real-time WebSocket server |
| **JWT (jsonwebtoken)** | 9.x | Stateless authentication tokens |
| **bcrypt** | 5.x | Secure password hashing |
| **Helmet** | 8.x | Security HTTP headers |
| **express-rate-limit** | 7.x | API rate limiting |
| **express-mongo-sanitize** | 2.x | NoSQL injection prevention |
| **Multer** | 1.x | File & image upload handling |
| **Winston** | 3.x | Structured production logging |
| **Docker + Compose** | — | Containerized deployment |

### ML Service (`/ml`) — Python 3.12

| Technology | Version | Purpose |
|---|---|---|
| **TensorFlow / Keras** | 2.17 / 3.8 | Deep learning model inference |
| **OpenCV** | 4.10 | Computer vision & camera input |
| **MediaPipe** | 0.10 | Hand gesture landmark detection |
| **Vosk** | 0.3.45 | Offline speech recognition |
| **SpeechRecognition + PyAudio** | — | Audio stream processing |
| **Flask** | 3.1 | ML service HTTP server |
| **OpenVINO** | 2024.4+ | Optimized model inference (gender detection) |
| **scikit-learn** | 1.6 | Gesture model training utilities |
| **PyMongo** | 4.x | Direct MongoDB writes from ML service |
| **PySerial** | 3.5 | Hardware buzzer/alert device communication |
| **pandas / matplotlib** | — | Data processing & visualization |

---

## 📁 Project Structure

```
backend/
├── api/                       # Node.js REST API & Socket.IO
│   ├── controllers/           # Business logic per route group
│   │   ├── user.controller.js
│   │   ├── admin.controller.js
│   │   ├── websos.controller.js
│   │   └── cctvsos.controller.js
│   ├── routes/                # Express route definitions
│   ├── middlewares/           # Auth, rate limiting, validation
│   ├── models/                # Mongoose schemas
│   ├── socket/                # Socket.IO server init & events
│   ├── utils/                 # Logger, helpers, ApiError
│   ├── db/                    # MongoDB connection
│   ├── public/                # Static file serving (images, CCTV)
│   ├── app.js                 # Express app entry point
│   ├── Dockerfile
│   └── .env.example
│
├── ml/                        # Python ML Edge Runtime
│   ├── app.py                 # Flask ML service entry point
│   ├── scripts/               # Training, evaluation, test scripts
│   │   ├── train_gesture_landmarks.py
│   │   ├── evaluate_gesture_landmarks.py
│   │   └── test_voice_sos.py
│   ├── data/models/           # Trained gesture & voice models
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile
│   └── .env.example
│
├── docker-compose.yml         # Orchestrates API + MongoDB (+ ML optional)
├── .env.api.example
├── .env.ml.example
└── README.md
```

---

## 🚀 Run Modes

### Mode 1 — API + MongoDB only *(recommended starting point)*

```bash
cd backend
docker compose up --build
```

| Service | URL |
|---|---|
| API | `http://localhost:8000` |
| MongoDB | `mongodb://localhost:27017` |

---

### Mode 2 — API + MongoDB + ML (all in Docker)

> Requires `/dev/video0` camera accessible inside Docker

```bash
docker compose --profile ml-container up --build
```

---

### Mode 3 — ML on host + API in Docker *(most reliable for camera access)*

```bash
# Terminal 1 — API + MongoDB
docker compose up --build

# Terminal 2 — ML service on host
cd ml
python3.12 app.py
```

---

### Mode 4 — Everything on host *(development)*

```bash
# Terminal 1 — MongoDB
mongod

# Terminal 2 — API
cd api && npm run dev

# Terminal 3 — ML service
cd ml && python3.12 app.py
```

---

## ⚙️ Environment Setup

```bash
# API environment
cp api/.env.example api/.env

# ML environment
cp .env.ml.example ml/.env
```

Key variables in `api/.env`:

```env
PORT=8000
MONGODB_URI=mongodb://127.0.0.1:27017/safestree
ACCESS_TOKEN_SECRET=your_secret
REFRESH_TOKEN_SECRET=your_secret
CORS_ORIGIN=http://localhost:5173
INTERNAL_ML_SERVICE_TOKEN=your_ml_token
OPENCAGE_API_KEY=optional_for_reverse_geocoding
```

---

## 🤖 ML Quickstart

Train a gesture and run the full detection pipeline:

```bash
cd ml

# 1. Train SOS gesture
./venv/bin/python scripts/train_gesture_landmarks.py --wizard --labels SOS,NEGATIVE --samples 160 --negative-samples 250

# 2. Evaluate gesture model
./venv/bin/python scripts/evaluate_gesture_landmarks.py

# 3. Test voice SOS offline
./venv/bin/python scripts/test_voice_sos.py --offline

# 4. Start ML service
python3.12 app.py
```

See [`ml/QUICKSTART_FULL_PIPELINE.md`](./ml/QUICKSTART_FULL_PIPELINE.md) for the complete guide.

---

## 🔗 Related Repositories

| Repository | Description | Link |
|---|---|---|
| 🎨 **Frontend** | React 19 + Vite user & admin UI | [safe-stree-frontend](https://github.com/ObaidGits/safe-stree-frontend) |
| 🌐 **Unified** | Full project with both as submodules | [safe-stree-unified](https://github.com/ObaidGits/safe-stree-unified) |

> For full architecture diagrams, deployment guides, and onboarding docs — visit the **[Unified Repository](https://github.com/ObaidGits/safe-stree-unified)**.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch — `git checkout -b feat/your-feature`
3. Commit your changes — `git commit -m "feat: add your feature"`
4. Push and open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](./LICENSE) for details.

---

<div align="center">

**Stay Safe. Stay Connected. 🛡️**

*Part of the [SafeStree](https://github.com/ObaidGits/safe-stree-unified) platform*

</div>

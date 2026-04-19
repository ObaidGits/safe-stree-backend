# SafeStree Backend Workspace

This folder unifies backend components:
- `api` for Node.js public backend
- `ml` for Python ML runtime

Frontend remains separate in `frontend`.

## Run Modes

### 1) API + Mongo only (recommended default)
Run from this folder:

- `docker compose up --build`

This starts:
- API at `http://localhost:8000`
- MongoDB at `mongodb://localhost:27017`

### 2) API + Mongo + ML container
If host camera is available in Docker, run:

- `docker compose --profile ml-container up --build`

If camera mapping fails in your environment, run ML on host and keep API in Compose.

### 3) ML on host + API in Compose
- Start API stack: `docker compose up --build`
- In another terminal: `cd ml && python3.12 app.py`

## Environment Files
- API example: `api/.env.example`
- ML env: `ml/.env`

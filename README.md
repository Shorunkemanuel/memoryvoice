# MemoryVoice

MemoryVoice turns a friend's spoken stories into structured, persistent memories.

Built for the Hacktoberfest Weekend 2026 challenge.

## Stack

- React + Vite + TypeScript
- Python + FastAPI
- Backboard Unified API
- faster-whisper
- Browser MediaRecorder

## Configuration

Use `.env.example` as a template for local settings. The backend reads configuration from its process environment and does not load `.env` files itself; provide those values to the backend process before starting it. Do not put real credentials in source control. The Vite development server proxies `/api` requests to `http://127.0.0.1:8000`. `VITE_API_URL` is optional locally and is used to set the API origin for a production frontend build. `FRONTEND_ORIGIN` sets the single allowed browser origin for the backend's production CORS policy.

## Render deployment

The root `render.yaml` defines a FastAPI web service and a Vite static site. Render builds the backend with `pip install -r requirements.txt` and starts it with Uvicorn bound to `0.0.0.0:$PORT`; it builds the frontend with `npm ci && npm run build` and publishes `frontend/dist`.

Create the Blueprint in Render and provide the requested Backboard values in the dashboard; no credentials are stored in this repository. Configure `VITE_API_URL` on the static site with the backend's public HTTPS origin (for example, `https://<your-api-service>.onrender.com`) and `FRONTEND_ORIGIN` on the API service with the static site's public HTTPS origin. Redeploy the static site after changing `VITE_API_URL`, because Vite embeds it during the build. The service URLs must be set to the actual URLs assigned by Render.

`DATABASE_URL` remains configured as SQLite, as in the existing application. Render's default filesystem is ephemeral; persistent database storage is not configured in this milestone.

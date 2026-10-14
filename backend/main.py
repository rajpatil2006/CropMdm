"""
CropMind API - entry point.

    start-backend.bat        (recommended: double-click or run from a terminal)
    python main.py           (same settings)
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

--host 0.0.0.0 is required for the ESP32 to reach the backend over Wi-Fi.

Routers:
    /api/auth     sign-up, login, own profile          (routers/auth.py)
    /api/sensors  ESP32 uploads + pump commands back    (routers/device.py)
    /api/...      device dashboards for farmers/admin   (routers/farm.py)
    /api/admin    admin console                         (routers/admin.py)
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from core import db
from routers import admin, auth, device, farm

app = FastAPI(title="CropMind API", version="2.0")

# Comma-separated list in .env when the dashboard is deployed elsewhere
origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(device.router)
app.include_router(farm.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"message": "CropMind API is running", "docs": "/docs"}


@app.get("/health")
def health():
    try:
        db.client.admin.command("ping")
        return {"status": "healthy", "database": "connected", "database_name": db.MONGODB_DATABASE}
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable") from exc


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 so the ESP32 on the same Wi-Fi can connect, not just this laptop
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

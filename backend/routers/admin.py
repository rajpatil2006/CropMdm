"""Admin console API: farmers, devices, all-farm overview, AI model, health and audit log."""

import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pymongo import DESCENDING

from core import audit, db
from core.security import admin_user, hash_device_key, hash_password, new_device_key, temporary_password
from farm_data import label_farm_decisions
from routers.auth import public_user
from schemas import DeviceCreate, DeviceUpdate
from services import farm_service as farm
from services.model_service import model_service
from export_training_data import EXCEL_PATH
from xai import FEATURE_KEYS

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


def _farmer(username):
    user = db.users.find_one({"_id": username})
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


# ---------------------------------------------------------------- farmers

@router.get("/users")
def list_users(status_filter: Optional[str] = Query(default=None, alias="status")):
    query = {"status": status_filter} if status_filter else {}
    out = []
    for user in db.users.find(query).sort("created_at", DESCENDING):
        row = public_user(user)
        row["devices"] = [d["_id"] for d in db.devices.find({"owner": user["_id"]}, {"_id": 1})]
        out.append(row)
    return out


@router.post("/users/{username}/{action}")
def user_action(username: str, action: Literal["approve", "reject", "disable", "enable", "reset-password"],
                admin=Depends(admin_user)):
    user = _farmer(username)
    if user["_id"] == admin["_id"] and action in ("disable", "reject"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot disable your own account")

    now = datetime.now(timezone.utc)
    result = {"username": username}
    if action == "approve":
        db.users.update_one({"_id": username}, {"$set": {"status": "active", "approved_at": now,
                                                         "approved_by": admin["_id"]}})
    elif action == "reject":
        db.users.update_one({"_id": username}, {"$set": {"status": "rejected"}})
    elif action == "disable":
        db.users.update_one({"_id": username}, {"$set": {"status": "disabled"}})
    elif action == "enable":
        db.users.update_one({"_id": username}, {"$set": {"status": "active"}})
    else:
        password = temporary_password()
        db.users.update_one({"_id": username}, {"$set": {"password_hash": hash_password(password),
                                                         "must_change_password": True}})
        result["temporary_password"] = password  # shown once to the admin
    audit.record(admin, f"user_{action.replace('-', '_')}", username)
    result["status"] = db.users.find_one({"_id": username})["status"]
    return result


# ---------------------------------------------------------------- devices

@router.get("/devices")
def list_devices():
    return [farm.device_summary(d) for d in db.devices.find().sort("_id", 1)]


@router.post("/devices", status_code=201)
def register_device(body: DeviceCreate, admin=Depends(admin_user)):
    if db.devices.find_one({"_id": body.device_id}):
        raise HTTPException(status.HTTP_409_CONFLICT, "A device with this ID is already registered")
    if body.owner:
        owner = _farmer(body.owner)
        if owner["role"] != "farmer" or owner["status"] != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Devices can only be assigned to active farmers")
    key = new_device_key()
    db.devices.insert_one({
        "_id": body.device_id,
        "name": body.name,
        "owner": body.owner or None,
        "key_hash": hash_device_key(key),
        "created_at": datetime.now(timezone.utc),
    })
    audit.record(admin, "device_register", body.device_id, {"owner": body.owner})
    # The key is shown once - it goes into the ESP32's secrets.h
    return {"device_id": body.device_id, "device_key": key}


@router.patch("/devices/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, admin=Depends(admin_user)):
    if not db.devices.find_one({"_id": device_id}):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    changes = {}
    if body.name is not None:
        changes["name"] = body.name
    if body.unassign:
        changes["owner"] = None
    elif body.owner:
        owner = _farmer(body.owner)
        if owner["role"] != "farmer" or owner["status"] != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Devices can only be assigned to active farmers")
        changes["owner"] = body.owner
    if changes:
        db.devices.update_one({"_id": device_id}, {"$set": changes})
        audit.record(admin, "device_update", device_id, changes)
    return farm.device_summary(db.devices.find_one({"_id": device_id}))


@router.post("/devices/{device_id}/key")
def regenerate_key(device_id: str, admin=Depends(admin_user)):
    if not db.devices.find_one({"_id": device_id}):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    key = new_device_key()
    db.devices.update_one({"_id": device_id}, {"$set": {"key_hash": hash_device_key(key)}})
    audit.record(admin, "device_new_key", device_id)
    return {"device_id": device_id, "device_key": key}


@router.delete("/devices/{device_id}")
def remove_device(device_id: str, admin=Depends(admin_user)):
    """Unregister a device. Its readings and decisions are kept."""
    if db.devices.delete_one({"_id": device_id}).deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    audit.record(admin, "device_remove", device_id)
    return {"removed": device_id}


@router.get("/unregistered-devices")
def unregistered_devices():
    """Device IDs that have sent data but are not registered (e.g. older firmware)."""
    registered = {d["_id"] for d in db.devices.find({}, {"_id": 1})}
    return sorted(d for d in db.readings.distinct("device_id") if d not in registered)


# ---------------------------------------------------------------- overview

@router.get("/overview")
def overview():
    devices = [farm.device_summary(d) for d in db.devices.find().sort("_id", 1)]
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    actions = {}
    for row in db.decisions.aggregate([
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": "$action", "n": {"$sum": 1}}},
    ]):
        actions[row["_id"]] = row["n"]
    return {
        "farmers_active": db.users.count_documents({"role": "farmer", "status": "active"}),
        "farmers_pending": db.users.count_documents({"role": "farmer", "status": "pending"}),
        "devices_total": len(devices),
        "devices_online": sum(1 for d in devices if d["online"]),
        "devices_unassigned": sum(1 for d in devices if not d["owner"]),
        "pump_commands_24h": db.pump_commands.count_documents({"created_at": {"$gte": since}}),
        "decisions_24h": actions,
        "devices": devices,
    }


# ---------------------------------------------------------------- AI model

@router.get("/model")
def model_details():
    meta = dict(model_service.meta)
    return {
        **meta,
        "farm_labels": db.training_labels.count_documents({}),
        "decisions_logged": db.decisions.count_documents({}),
        "retrain": model_service.retrain_status,
    }


@router.post("/model/label-farm-data")
def label_farm_data(admin=Depends(admin_user)):
    """Label logged decisions older than 48 h from what the sensors saw afterwards."""
    totals = {"labelled": 0, "skipped": 0}
    for device in db.devices.find():
        config = farm.load_config(device["_id"])
        result = label_farm_decisions(db.db, FEATURE_KEYS, config.latitude, config.longitude)
        totals["labelled"] += result["labelled"]
        totals["skipped"] += result["skipped"]
    totals["total_farm_labels"] = db.training_labels.count_documents({})
    audit.record(admin, "label_farm_data", details=totals)
    return totals


@router.get("/model/training-data")
def training_data(admin=Depends(admin_user)):
    """Excel workbook of exactly the data the current model was trained on."""
    if not os.path.exists(EXCEL_PATH):
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Training data file not found. Run `python export_training_data.py` and redeploy.")
    audit.record(admin, "download_training_data")
    return FileResponse(EXCEL_PATH, filename="CropMind_training_data.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/model/retrain", status_code=202)
def retrain(admin=Depends(admin_user)):
    if os.getenv("ALLOW_RETRAIN", "true").lower() == "false":
        # Free hosting has ~512 MB RAM; training needs several GB
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Retraining is disabled on this server (not enough memory). Run "
                            "`python train_model.py --label-farm` on a laptop and redeploy the model file.")
    if not model_service.start_retrain(label_farm=True):
        raise HTTPException(status.HTTP_409_CONFLICT, "Retraining is already running")
    audit.record(admin, "model_retrain")
    return model_service.retrain_status


# ---------------------------------------------------------------- health + audit

@router.get("/health")
def health():
    now = datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    try:
        db.client.admin.command("ping")
        database = "connected"
    except Exception as exc:  # noqa: BLE001 - report, don't fail the health page
        database = f"error: {exc}"

    devices = [farm.device_summary(d) for d in db.devices.find()]
    problem_commands = []
    for c in db.pump_commands.find({"created_at": {"$gte": week}}).sort("created_at", DESCENDING).limit(200):
        state = c["status"]
        if state in ("queued", "delivered") and c["expires_at"] < now:
            state = "expired" if state == "queued" else "no reply"
        if state in ("expired", "no reply", "rejected"):
            problem_commands.append({"id": c["_id"], "device_id": c["device_id"], "action": c["action"],
                                     "source": c.get("source"), "status": state,
                                     "detail": c.get("ack_detail"), "created_at": farm.iso(c["created_at"])})

    forecasts = [{"location": w["_id"], "fetched_at": farm.iso(w["fetched_at"]),
                  "age_hours": round((now - w["fetched_at"]).total_seconds() / 3600, 1)}
                 for w in db.weather_cache.find({}, {"fetched_at": 1})]

    return {
        "database": database,
        "model": {"trained_at": model_service.meta.get("trained_at"), "retrain": model_service.retrain_status},
        "devices_offline": [d for d in devices if not d["online"]],
        "problem_commands": problem_commands[:50],
        "forecast_cache": forecasts,
        "farmers_pending": db.users.count_documents({"status": "pending"}),
    }


@router.get("/audit")
def audit_trail(limit: int = Query(default=100, ge=1, le=1000), actor: Optional[str] = None):
    query = {"actor": actor} if actor else {}
    return [farm.serialize(doc) for doc in db.audit_log.find(query).sort("at", DESCENDING).limit(limit)]

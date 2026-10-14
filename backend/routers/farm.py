"""
Device-scoped farm API used by both dashboards. A farmer only reaches devices
assigned to them; an admin reaches every device.
"""

from functools import wraps

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from core import audit, db
from core.security import current_user, device_for_user
from crops import catalogue
from schemas import FarmConfig, PumpCommand
from services import farm_service as farm
from services.model_service import model_service

router = APIRouter(prefix="/api", tags=["farm"])


def db_errors(fn):
    """Turn database outages into a clean 503 instead of a stack trace."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PyMongoError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable") from exc
    return wrapper


@router.get("/crops")
def list_crops(user=Depends(current_user)):
    return catalogue()


@router.get("/model/summary")
def model_summary(user=Depends(current_user)):
    """Plain facts about the AI model, shown under each explanation."""
    meta = model_service.meta
    evaluation = meta.get("evaluation", {})
    return {
        "trained_at": meta.get("trained_at"),
        "trained_on": meta.get("trained_on"),
        "replay_decisions": meta.get("replay_decisions"),
        "farm_decisions": meta.get("farm_decisions"),
        "evaluation": {k: evaluation.get(k) for k in (
            "holdout_locations", "model_accuracy", "rule_accuracy", "model_rain_wait", "rule_rain_wait")},
    }


@router.get("/devices")
@db_errors
def my_devices(user=Depends(current_user)):
    query = {} if user["role"] == "admin" else {"owner": user["_id"]}
    return [farm.device_summary(d) for d in db.devices.find(query).sort("_id", 1)]


@router.get("/devices/{device_id}")
@db_errors
def device_detail(device_id: str, user=Depends(current_user)):
    return farm.device_summary(device_for_user(device_id, user))


@router.get("/devices/{device_id}/readings/latest")
@db_errors
def latest_reading(device_id: str, user=Depends(current_user)):
    device_for_user(device_id, user)
    return farm.serialize(farm.latest_reading(device_id)) or {}


@router.get("/devices/{device_id}/readings")
@db_errors
def reading_history(device_id: str, limit: int = Query(default=100, ge=1, le=1000), user=Depends(current_user)):
    device_for_user(device_id, user)
    cursor = db.readings.find({"device_id": device_id}).sort("timestamp", DESCENDING).limit(limit)
    return [farm.serialize(doc) for doc in cursor]


@router.get("/devices/{device_id}/config")
@db_errors
def get_config(device_id: str, user=Depends(current_user)):
    device_for_user(device_id, user)
    return farm.load_config(device_id)


@router.put("/devices/{device_id}/config")
@db_errors
def put_config(device_id: str, config: FarmConfig, user=Depends(current_user)):
    device_for_user(device_id, user)
    config.device_id = device_id
    # Auto-irrigation has its own switch; keep its current value here
    current = farm.load_config(device_id)
    config.auto_irrigation = current.auto_irrigation
    config.sensor_checks = current.sensor_checks
    farm.save_config(config)
    audit.record(user, "update_crop_settings", device_id,
                 {"crop": config.crop, "soil": config.soil_type, "sowing_date": config.sowing_date.isoformat()})
    return config


@router.get("/devices/{device_id}/crop-status")
@db_errors
def crop_status(device_id: str, user=Depends(current_user)):
    device_for_user(device_id, user)
    return farm.crop_status(device_id)


@router.get("/devices/{device_id}/weather")
@db_errors
def weather(device_id: str, refresh: bool = False, user=Depends(current_user)):
    device_for_user(device_id, user)
    return farm.weather_view(device_id, refresh)


@router.get("/devices/{device_id}/decision")
@db_errors
def decision(device_id: str, user=Depends(current_user)):
    device_for_user(device_id, user)
    decision = farm.serialize(farm.compute_decision(device_id))
    decision["pump_state"] = farm.pump_state(device_id)
    return decision


@router.get("/devices/{device_id}/decisions")
@db_errors
def decision_history(device_id: str, limit: int = Query(default=30, ge=1, le=500), user=Depends(current_user)):
    device_for_user(device_id, user)
    cursor = (db.decisions.find({"device_id": device_id},
                                {"state": 0, "explanation": 0, "rule": 0})
              .sort("timestamp", DESCENDING).limit(limit))
    return [farm.serialize(doc) for doc in cursor]


@router.get("/devices/{device_id}/pump")
@db_errors
def pump_status(device_id: str, user=Depends(current_user)):
    device_for_user(device_id, user)
    return farm.pump_view(device_id)


@router.post("/devices/{device_id}/pump/command")
@db_errors
def pump_command(device_id: str, body: PumpCommand, user=Depends(current_user)):
    """Manual pump control - only while automatic irrigation is off (one rule at a time)."""
    device_for_user(device_id, user)
    if farm.load_config(device_id).auto_irrigation:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Automatic irrigation is ON, so the pump follows the decision. "
                            "Turn automatic irrigation off to control the pump yourself.")
    try:
        sent = farm.pump.send(device_id, body.action, body.seconds,
                              source="farmer" if user["role"] == "farmer" else "admin", by=user["_id"])
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    audit.record(user, "pump_command", device_id, {"action": body.action, "seconds": sent["seconds"]})
    return {"id": sent["_id"], "action": sent["action"], "seconds": sent["seconds"], "status": sent["status"]}


@router.put("/devices/{device_id}/pump/auto")
@db_errors
def set_auto(device_id: str, enabled: bool, user=Depends(current_user)):
    device_for_user(device_id, user)
    config = farm.load_config(device_id)
    config.auto_irrigation = enabled
    farm.save_config(config)
    run = farm.pump.active_run(device_id)
    if not enabled and run and run.get("source") == "ai":
        # Switching automatic irrigation off stops its run right away
        farm.pump.send(device_id, "OFF", source="ai", reason="Automatic irrigation switched off", by=user["_id"])
    audit.record(user, "auto_irrigation", device_id, {"enabled": enabled})
    return {"device_id": device_id, "auto_irrigation": enabled}


@router.put("/devices/{device_id}/sensor-checks")
@db_errors
def set_sensor_checks(device_id: str, enabled: bool, user=Depends(current_user)):
    """Turn sensor fault checks on/off (off only for bench tests without a pot)."""
    device_for_user(device_id, user)
    config = farm.load_config(device_id)
    config.sensor_checks = enabled
    farm.save_config(config)
    audit.record(user, "sensor_checks", device_id, {"enabled": enabled})
    return {"device_id": device_id, "sensor_checks": enabled}

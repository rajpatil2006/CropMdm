"""
ESP32 endpoint. Each upload is authenticated with the device's own key
(X-Device-Key header); the response carries the next pump command, if any.
"""

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, status
from pymongo.errors import PyMongoError

from core import db
from core.security import hash_device_key
from schemas import SensorReading
from services.farm_service import auto_decide, pump

router = APIRouter(prefix="/api/sensors", tags=["device"])


def check_device_key(device_id, key):
    device = db.devices.find_one({"_id": device_id})
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device is not registered - ask the admin to add it")
    if not key or not hmac.compare_digest(device.get("key_hash", ""), hash_device_key(key)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong device key")
    return device


@router.post("/readings")
def receive_sensor_reading(reading: SensorReading, x_device_key: str = Header(default="")):
    check_device_key(reading.device_id, x_device_key)
    try:
        data = reading.model_dump(exclude_none=True)
        acks = data.pop("acks", None)
        if not data.get("timestamp"):
            data["timestamp"] = datetime.now(timezone.utc)
        result = db.readings.insert_one(data)
        pump.handle_acks(data["device_id"], acks)
    except PyMongoError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not save sensor reading") from exc

    auto = auto_decide(data["device_id"])
    try:
        command = pump.next_command(data["device_id"])
    except PyMongoError:
        command = None

    # The ESP32 reads "command" from this response and runs the pump
    return {
        "status": "received",
        "id": str(result.inserted_id),
        "device_id": data["device_id"],
        "auto": auto,
        "command": command,
    }

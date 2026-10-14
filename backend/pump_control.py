"""
Pump control over the ESP32's own HTTP connection - no broker, no external service.

The ESP32 sits behind the farm's Wi-Fi router, so the backend cannot connect
to it. Instead, every sensor upload (POST /api/sensors/readings, every few
seconds) gets the next pending pump command in its response, and the ESP32
reports what it did with that command in its next upload:

    dashboard / AI  -> queue command in MongoDB
    ESP32 upload    -> response carries {"command": {"id", "action", "seconds"}}
    next upload     -> {"acks": [{"id", "status": "started" | "done" | ...}]}

Safety rules built in:
  * every ON command carries a run time; the ESP32 switches off on its own timer
  * commands expire after COMMAND_TTL, so a pump never starts long after the click
  * a newer command cancels older undelivered ones (the latest intent wins)
"""

import uuid
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING, DESCENDING

COMMAND_TTL = timedelta(seconds=60)
REDELIVER_AFTER = timedelta(seconds=15)   # resend if the ESP32 never confirmed
ONLINE_WITHIN = timedelta(seconds=30)     # ESP32 counts as online if it uploaded this recently
MAX_RUN_SECONDS = 600
ACK_STATUSES = ("started", "done", "stopped", "rejected")


class PumpController:
    def __init__(self, db):
        self.commands = db["pump_commands"]
        self.readings = db["sensor_readings"]
        self.commands.create_index([("device_id", ASCENDING), ("created_at", DESCENDING)])

    # ------------------------------------------------------------ farmer / AI side

    def send(self, device_id, action, seconds=0, source="farmer", reason=None, by=None):
        """Queue a command for the ESP32's next upload."""
        if action not in ("ON", "OFF"):
            raise ValueError("action must be ON or OFF")
        seconds = int(min(max(seconds, 0), MAX_RUN_SECONDS)) if action == "ON" else 0
        if action == "ON" and seconds <= 0:
            raise ValueError("ON needs a run time in seconds")

        now = datetime.now(timezone.utc)
        # The latest intent wins: drop anything still waiting to be delivered
        self.commands.update_many(
            {"device_id": device_id, "status": {"$in": ["queued", "delivered"]}, "acked": {"$ne": True}},
            {"$set": {"status": "cancelled", "cancelled_at": now}},
        )
        command = {
            "_id": uuid.uuid4().hex[:12],
            "device_id": device_id,
            "action": action,
            "seconds": seconds,
            "source": source,
            "reason": reason,
            "by": by,
            "created_at": now,
            "expires_at": now + COMMAND_TTL,
            "status": "queued",
        }
        self.commands.insert_one(command)
        return command

    # ------------------------------------------------------------ ESP32 side

    def handle_acks(self, device_id, acks):
        """Apply the ESP32's reports about commands it received."""
        now = datetime.now(timezone.utc)
        for ack in acks or []:
            status = ack.get("status")
            if status not in ACK_STATUSES or not ack.get("id"):
                continue
            self.commands.update_one(
                {"_id": ack["id"], "device_id": device_id},
                {"$set": {"status": status, "acked": True, f"{status}_at": now,
                          "ack_detail": ack.get("detail")}},
            )

    def next_command(self, device_id):
        """The command to hand to the ESP32 in this upload's response, if any."""
        now = datetime.now(timezone.utc)
        command = self.commands.find_one(
            {
                "device_id": device_id,
                "expires_at": {"$gt": now},
                "acked": {"$ne": True},
                "$or": [
                    {"status": "queued"},
                    {"status": "delivered", "delivered_at": {"$lt": now - REDELIVER_AFTER}},
                ],
            },
            sort=[("created_at", DESCENDING)],
        )
        if command is None:
            return None
        self.commands.update_one(
            {"_id": command["_id"]}, {"$set": {"status": "delivered", "delivered_at": now}}
        )
        return {"id": command["_id"], "action": command["action"], "seconds": command["seconds"]}

    # ------------------------------------------------------------ status

    def last_contact(self, device_id):
        doc = self.readings.find_one(
            {"device_id": device_id}, {"timestamp": 1}, sort=[("timestamp", DESCENDING)]
        )
        return doc.get("timestamp") if doc else None

    def active_run(self, device_id, now=None):
        """The ON command that is still queued or running (with its end time), else None."""
        now = now or datetime.now(timezone.utc)
        last = self.commands.find_one(
            {"device_id": device_id, "action": {"$in": ["ON", "OFF"]},
             "status": {"$nin": ["cancelled", "rejected", "expired"]}},
            sort=[("created_at", DESCENDING)],
        )
        if last is None or last["action"] != "ON" or last["status"] not in ("queued", "delivered", "started"):
            return None  # nothing running, or the newest command was an OFF
        if last["status"] != "started" and last["expires_at"] < now:
            return None  # never reached the device
        ends = last["created_at"] + timedelta(seconds=last["seconds"] + 30)
        return {**last, "ends": ends} if now < ends else None

    def running_until(self, device_id, now=None):
        run = self.active_run(device_id, now)
        return run["ends"] if run else None

    def status(self, device_id, limit=10):
        now = datetime.now(timezone.utc)
        contact = self.last_contact(device_id)
        recent = list(self.commands.find({"device_id": device_id}).sort("created_at", -1).limit(limit))
        for c in recent:
            if c["status"] == "queued" and c["expires_at"] < now:
                c["status"] = "expired"
            elif c["status"] == "delivered" and c["expires_at"] < now:
                c["status"] = "no reply"
        return {
            "device_online": contact is not None and now - contact < ONLINE_WITHIN,
            "last_contact": contact,
            "seconds_since_contact": int((now - contact).total_seconds()) if contact else None,
            "recent_commands": recent,
        }

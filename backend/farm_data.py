"""
Real farm data for training (synopsis 3.5: validate decisions with later sensor feedback).

Every decision the system makes is logged with its full input state. Once 48 h
have passed, `label_farm_decisions` judges what the right action was:

  * soil still had readily available water        -> NO_IRRIGATION
  * pump did not run: the measured soil moisture shows whether rain refilled
    the root zone before the crop passed its safe limit -> WAIT_FOR_RAIN / IRRIGATE
  * pump ran: the counterfactual cannot be measured, so the actual rainfall
    at the farm (Open-Meteo archive) is replayed through hindsight_label

Labelled rows go to the `training_labels` collection, together with any
validated farmer overrides (source="override"), and are used by train_model.py.
"""

from datetime import datetime, timedelta, timezone

import requests

from crops import depletion_mm
from water_balance import RAIN_COVER_FRACTION, hindsight_label

WINDOW = timedelta(hours=48)
MIN_READINGS = 6


def _actual_rain(lat, lon, start, end):
    response = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": lat, "longitude": lon, "timezone": "UTC",
        "start_date": start.date().isoformat(), "end_date": end.date().isoformat(),
        "hourly": "precipitation",
    }, timeout=60)
    response.raise_for_status()
    hourly = response.json()["hourly"]
    rain = {}
    for t, mm in zip(hourly["time"], hourly["precipitation"]):
        rain[datetime.fromisoformat(t).replace(tzinfo=timezone.utc)] = mm or 0.0
    first = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return [rain.get(first + timedelta(hours=k), 0.0) for k in range(48)]


def _label_from_readings(state, readings):
    """Label from the measured soil moisture trajectory (no irrigation happened)."""
    fc, wp, zr = state["field_capacity_pct"], state["wilting_point_pct"], state["root_depth_mm"]
    target = state["depletion_mm"] * (1 - RAIN_COVER_FRACTION)
    for r in readings:
        if r.get("soil_moisture_pct") is None:
            continue
        d = depletion_mm(r["soil_moisture_pct"], fc, wp, zr)
        if d > state["safe_wait_limit_mm"]:
            return "IRRIGATE"
        if d <= target:
            return "WAIT_FOR_RAIN"
    return "IRRIGATE"


def label_farm_decisions(db, feature_keys, latitude, longitude, now=None):
    now = now or datetime.now(timezone.utc)
    decisions = db["decisions"].find({
        "status": "ok",
        "action": {"$ne": "VERIFY"},
        "labelled": {"$ne": True},
        "timestamp": {"$lte": now - WINDOW},
    })
    added = skipped = 0

    for dec in decisions:
        state = dec.get("state") or {}
        if any(k not in state for k in feature_keys):
            skipped += 1   # logged by an older version without these features
            db["decisions"].update_one({"_id": dec["_id"]}, {"$set": {"labelled": True, "label": None}})
            continue

        start = dec["reading_timestamp"]
        readings = list(db["sensor_readings"].find(
            {"device_id": dec["device_id"], "timestamp": {"$gt": start, "$lte": start + WINDOW}}
        ).sort("timestamp", 1))
        if len(readings) < MIN_READINGS:
            skipped += 1
            continue

        if state["depletion_mm"] < state["raw_mm"]:
            label, method = "NO_IRRIGATION", "soil water"
        elif not any(r.get("relay_on") for r in readings):
            label, method = _label_from_readings(state, readings), "measured soil moisture"
        else:
            try:
                rain = _actual_rain(latitude, longitude, start, start + WINDOW)
            except requests.RequestException:
                skipped += 1
                continue
            etc_hourly = [state["etc_mm_day"] / 24] * 48
            label = hindsight_label(state["depletion_mm"], state["raw_mm"],
                                    state["safe_wait_limit_mm"], etc_hourly, rain)
            method = "actual rainfall"

        db["training_labels"].insert_one({
            "source": "farm",
            "device_id": dec["device_id"],
            "decision_timestamp": dec["timestamp"],
            "features": {k: state[k] for k in feature_keys},
            "label": label,
            "label_method": method,
            "system_action": dec["action"],
            "labelled_at": now,
        })
        db["decisions"].update_one({"_id": dec["_id"]}, {"$set": {"labelled": True, "label": label}})
        added += 1

    return {"labelled": added, "skipped": skipped}


def load_farm_rows(db, feature_keys):
    rows = []
    for doc in db["training_labels"].find({"label": {"$in": ["IRRIGATE", "WAIT_FOR_RAIN", "NO_IRRIGATION"]}}):
        feats = doc.get("features", {})
        if all(k in feats for k in feature_keys):
            rows.append((feats, doc["label"], doc.get("source", "farm")))
    return rows

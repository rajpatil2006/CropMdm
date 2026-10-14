"""
Per-device farm logic: crop settings, weather, the AI irrigation decision and
automatic pump control. Used by the farmer/admin API and the ESP32 upload.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from pymongo import DESCENDING
from requests import RequestException

import weather as wx
from core import db
from crops import growth_stage, resolve_crop, root_zone
from messages import msg, render
from pump_control import PumpController
from schemas import FarmConfig
from services.model_service import model_service
from water_balance import ACTION_LABELS, build_state, check_inputs, final_decision, pump_plan, rule_decision

WEATHER_REFRESH_MINUTES = 60
AUTO_DECISION_INTERVAL = timedelta(seconds=10)  # how often automatic irrigation re-decides
PUMP_BLOCK_SECONDS = 60        # each automatic ON lasts this long ...
RENEW_BEFORE = timedelta(seconds=30)  # ... and is renewed this long before it ends
ONLINE_WITHIN = timedelta(seconds=30)
DECISION_LOG_EVERY = timedelta(minutes=5)

# Pump commands ride on the ESP32's own sensor uploads (no broker needed)
pump = PumpController(db.db)
_last_auto_decision = {}


# ---------------------------------------------------------------- helpers

def iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def serialize(document):
    """MongoDB document -> JSON-friendly dict."""
    if document is None:
        return None
    out = {}
    for key, value in document.items():
        if key == "_id":
            out["id"] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, dict):
            out[key] = serialize(value)
        elif isinstance(value, list):
            out[key] = [serialize(v) if isinstance(v, dict) else iso(v) for v in value]
        else:
            out[key] = value
    return out


def latest_reading(device_id):
    return db.readings.find_one({"device_id": device_id}, sort=[("timestamp", DESCENDING)])


def device_summary(device):
    """Card data for one device: owner, latest reading, online state, last decision."""
    reading = latest_reading(device["_id"])
    last_decision = db.decisions.find_one(
        {"device_id": device["_id"]}, {"action": 1, "timestamp": 1}, sort=[("timestamp", DESCENDING)]
    )
    config = load_config(device["_id"])
    now = datetime.now(timezone.utc)
    ts = reading.get("timestamp") if reading else None
    return {
        "device_id": device["_id"],
        "name": device.get("name"),
        "owner": device.get("owner"),
        "crop": config.crop if config.crop != "custom" else (config.custom_crop.name if config.custom_crop else "custom"),
        "auto_irrigation": config.auto_irrigation,
        "online": ts is not None and now - ts < ONLINE_WITHIN,
        "last_seen": iso(ts),
        "seconds_since_seen": int((now - ts).total_seconds()) if ts else None,
        "soil_moisture_pct": reading.get("soil_moisture_pct") if reading else None,
        "temperature": reading.get("temperature") if reading else None,
        "humidity": reading.get("humidity") if reading else None,
        "relay_on": reading.get("relay_on") if reading else None,
        "last_action": last_decision.get("action") if last_decision else None,
        "last_action_at": iso(last_decision.get("timestamp")) if last_decision else None,
    }


# ---------------------------------------------------------------- crop config

def load_config(device_id):
    document = db.farm_config.find_one({"_id": device_id})
    if document is None:
        return FarmConfig(device_id=device_id)
    document.pop("_id", None)
    document["device_id"] = device_id
    return FarmConfig(**document)


def save_config(config):
    data = config.model_dump()
    data["sowing_date"] = config.sowing_date.isoformat()
    db.farm_config.replace_one({"_id": config.device_id}, data, upsert=True)
    return config


def crop_status(device_id):
    config = load_config(device_id)
    weather = weather_summary(config)
    et0, et0_source = resolve_et0(config, weather, device_id)
    config_dict = config.model_dump()
    crop = resolve_crop(config_dict)
    stage = growth_stage(crop, config.sowing_date)
    etc = et0 * stage["kc"]
    return {
        "crop": config.crop,
        "crop_name": crop["name"],
        "crop_p": crop["p"],
        "stress_tolerance": crop["stress_tolerance"],
        "soil_type": config.soil_type,
        **stage,
        "et0_mm": round(et0, 2),
        "et0_source": et0_source,
        "etc_mm_day": round(etc, 2),
        **root_zone(config_dict, crop, etc),
    }


# ---------------------------------------------------------------- weather

def weather_summary(config, force_refresh=False):
    """Forecast for the farm, cached in MongoDB so the API is hit at most hourly."""
    key = f"{config.latitude:.2f},{config.longitude:.2f}"
    now = datetime.now(timezone.utc)
    cached = db.weather_cache.find_one({"_id": key})

    fresh_enough = cached is not None and now - cached["fetched_at"] < timedelta(minutes=WEATHER_REFRESH_MINUTES)
    if fresh_enough and not force_refresh:
        return wx.summarise(cached["raw"], cached["fetched_at"], now)

    try:
        raw = wx.fetch_forecast(config.latitude, config.longitude)
        db.weather_cache.replace_one({"_id": key}, {"_id": key, "raw": raw, "fetched_at": now}, upsert=True)
        return wx.summarise(raw, now, now)
    except (RequestException, ValueError, KeyError) as exc:
        if cached is not None:
            # Offline: keep using the last forecast; its age downgrades reliability
            summary = wx.summarise(cached["raw"], cached["fetched_at"], now)
            summary["fetch_error"] = str(exc)
            return summary
        return wx.unavailable(f"Forecast fetch failed: {exc}")


def recent_sensor_summary(device_id):
    """Last 24 h of DHT11 data: all temperatures, max temperature, mean humidity."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    docs = list(db.readings.find(
        {"device_id": device_id, "timestamp": {"$gte": since}}, {"temperature": 1, "humidity": 1}
    ))
    temps = [d.get("temperature") for d in docs if d.get("temperature") is not None]
    hums = [d.get("humidity") for d in docs if d.get("humidity") is not None]
    return {
        "temps": temps,
        "tmax": max(temps) if temps else None,
        "humidity": sum(hums) / len(hums) if hums else None,
    }


def resolve_et0(config, weather, device_id, sensor=None):
    sensor = sensor or recent_sensor_summary(device_id)
    return wx.resolve_et0(weather, sensor["temps"], config.latitude, date.today().timetuple().tm_yday)


def weather_view(device_id, refresh=False):
    config = load_config(device_id)
    summary = weather_summary(config, force_refresh=refresh)
    et0, et0_source = resolve_et0(config, summary, device_id)
    return {**summary, "latitude": config.latitude, "longitude": config.longitude,
            "et0_used_mm": round(et0, 2), "et0_source": et0_source}


# ---------------------------------------------------------------- AI decision

def _water_message(state):
    params = {
        "used": round(state["depletion_mm"], 1),
        "raw": round(state["raw_mm"], 1),
        "crop": state["crop_name"].lower(),
        "crop_key": state["crop"],
        "stage": state["stage"],
    }
    if state["depletion_mm"] < state["raw_mm"]:
        return msg("water.ok", hours=round(state["hours_to_stress"]), **params)
    return msg("water.stressed", hours=round(state["hours_safe_wait"]), **params)


def compute_decision(device_id):
    config = load_config(device_id)
    reading = latest_reading(device_id)
    if reading is None:
        return {"status": "no_data", "device_id": device_id}

    now = datetime.now(timezone.utc)
    weather = weather_summary(config)
    sensor = recent_sensor_summary(device_id)
    et0, et0_source = resolve_et0(config, weather, device_id, sensor)
    config_dict = config.model_dump()
    now_local = now + timedelta(seconds=weather.get("utc_offset_seconds", 0))

    problems = check_inputs(reading, now, config.sensor_checks)
    state = build_state(reading, config_dict, weather, et0, now_local, sensor)
    rule = model = explanation = None
    decided_by = None
    plan = {"volume_ml": 0, "pump_seconds": 0}

    if problems:
        # Untrusted input: hold the pump off and ask the farmer to check
        action = "VERIFY"
        reasons = problems + [msg("trust.hold")]
    else:
        # Forecast-trusting rule: shown for comparison, not used to decide
        rule = rule_decision(
            state,
            rain_probability_threshold=config.rain_probability_threshold,
            rain_cover_fraction=config.rain_cover_fraction,
        )
        model_action, probabilities = model_service.predict(state)
        action, decided_by, guard_key = final_decision(state, model_action, probabilities)

        reasons = [_water_message(state)]
        if action == "WAIT_FOR_RAIN":
            reasons.append(msg("ai.wait", hours=round(state["hours_safe_wait"]),
                               conf=round(100 * probabilities.get("WAIT_FOR_RAIN", 0))))
        elif action == "IRRIGATE" and state["hours_safe_wait"] > 0:
            reasons.append(msg("ai.irrigate", conf=round(100 * probabilities.get("IRRIGATE", 0))))
        if guard_key:
            reasons.append(msg(guard_key))
        if rule["action"] != action:
            reasons.append(msg("rule.differs", action=rule["action"]))

        model = {"action": model_action, "probabilities": probabilities,
                 "confidence": probabilities.get(action, 0.0)}
        explanation = model_service.explain(state, action)
        if action == "IRRIGATE":
            plan = pump_plan(state["depletion_mm"], config_dict)

    if not config.sensor_checks:
        reasons.append(msg("trust.checks_off"))

    decision = {
        "status": "ok",
        "device_id": device_id,
        "timestamp": now,
        "reading_id": str(reading["_id"]),
        "reading_timestamp": reading.get("timestamp"),
        "action": action,
        "action_label": ACTION_LABELS[action],
        "pump_command": "ON" if action == "IRRIGATE" else "OFF",
        **plan,
        "reasons": reasons,
        "reasons_text": [render(r) for r in reasons],
        "trust_problems": problems,
        "decided_by": decided_by,
        "irrigation_mm": state["depletion_mm"] if action == "IRRIGATE" else 0.0,
        "rule": rule,
        "model": model,
        "explanation": explanation,
        "state": state,
        "et0_source": et0_source,
        "forecast_reliability": weather.get("reliability"),
    }

    # Log a decision when it changes, otherwise at most every DECISION_LOG_EVERY
    # (each one is ~4.5 KB; logging every reading would fill a free 512 MB database in ~2 weeks)
    last = db.decisions.find_one({"device_id": device_id}, {"action": 1, "timestamp": 1, "reading_id": 1},
                                 sort=[("timestamp", DESCENDING)])
    if (last is None
            or last.get("action") != action
            or (last.get("reading_id") != decision["reading_id"] and now - last["timestamp"] >= DECISION_LOG_EVERY)):
        db.decisions.insert_one(dict(decision))
    return decision


def auto_decide(device_id):
    """
    Automatic irrigation: the pump simply follows the decision.

        "Irrigate now"      -> pump ON  (kept on in short blocks while it lasts)
        any other decision  -> pump OFF

    Runs on every sensor upload (at most every AUTO_DECISION_INTERVAL). Commands
    reach the ESP32 in the response to its next upload. A run started manually
    by the farmer/admin is their override and is left alone. Never lets a
    decision problem break sensor ingestion.
    """
    now = datetime.now(timezone.utc)
    last = _last_auto_decision.get(device_id)
    if last is not None and now - last < AUTO_DECISION_INTERVAL:
        return None
    _last_auto_decision[device_id] = now

    try:
        config = load_config(device_id)
        decision = compute_decision(device_id)
        action = decision.get("action")
        result = {"action": action, "pump_command": None}

        run = pump.active_run(device_id, now)
        cropmind_run = run is not None and run.get("source") == "ai"
        manual_run = run is not None and not cropmind_run

        if not config.auto_irrigation:
            if cropmind_run:  # automatic irrigation was switched off mid-run
                pump.send(device_id, "OFF", source="ai", reason="Automatic irrigation switched off")
                result["pump_command"] = "sent OFF (auto-irrigation off)"
            return result

        if action == "IRRIGATE":
            if manual_run:
                return result
            # Keep the pump on: renew the block before the current one runs out
            ends = run["created_at"] + timedelta(seconds=run["seconds"]) if cropmind_run else None
            if ends is None or ends - now <= RENEW_BEFORE:
                pump.send(device_id, "ON", PUMP_BLOCK_SECONDS, source="ai",
                          reason=" ".join(decision["reasons_text"][:1]))
                result["pump_command"] = f"sent ON {PUMP_BLOCK_SECONDS} s"
        elif cropmind_run:
            pump.send(device_id, "OFF", source="ai", reason=f"Decision changed to {action}")
            result["pump_command"] = "sent OFF"
        return result
    except Exception as exc:  # noqa: BLE001 - ingestion must keep working
        logging.exception("Automatic decision failed")
        return {"error": str(exc)}


def pump_state(device_id, config=None):
    """Whether automatic irrigation will act on the decision - shown under it."""
    config = config or load_config(device_id)
    return {"auto_irrigation": config.auto_irrigation, "sensor_checks": config.sensor_checks,
            "pump_running": pump.active_run(device_id) is not None}


def pump_view(device_id):
    status = pump.status(device_id)
    config = load_config(device_id)
    status["last_contact"] = iso(status["last_contact"])
    status["recent_commands"] = [
        {**{k: iso(v) for k, v in c.items() if k != "_id"}, "id": c["_id"]} for c in status["recent_commands"]
    ]
    status["auto_irrigation"] = config.auto_irrigation
    status["sensor_checks"] = config.sensor_checks
    return status

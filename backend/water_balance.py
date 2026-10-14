"""
Steps 1 + 2 combined - crop- and weather-aware water balance (synopsis section 3.2).

    ETc = ET0 x Kc                                                    (eq. 1)
    Irrigation requirement ~ crop demand - effective rain - soil water (eq. 2)

* `build_state`    - live sensor reading + crop config + forecast -> flat numbers
* `rule_decision`  - transparent forecast-trusting rule (the baseline)
* `hindsight_label`- the correct action judged from what actually happened next
                     (used to label historical replays and real farm decisions)
* `final_decision` - AI model choice bounded by agronomic safety guards
"""

from crops import adjusted_p, depletion_mm, growth_stage, resolve_crop, root_zone

ACTIONS = ["IRRIGATE", "WAIT_FOR_RAIN", "NO_IRRIGATION"]
ACTION_LABELS = {
    "IRRIGATE": "Irrigate now",
    "WAIT_FOR_RAIN": "Wait for rain",
    "NO_IRRIGATION": "No irrigation needed",
    "VERIFY": "Verification required",
}

NO_RAIN_HOURS = 72.0          # stands in for "no rain within the forecast window"
MAX_WAIT_HOURS = 240.0        # cap for "hours the crop can wait"
RAIN_NOW_WETNESS_PCT = 50.0   # rain-sensor wetness that counts as "raining now"
RAIN_EFFICIENCY = 0.8         # share of rain that reaches the root zone
MIN_EFFECTIVE_RAIN_MM = 1.0   # lighter showers are ignored
MAX_READING_AGE_MIN = 15
SOIL_ADC_MAX = 4095           # ESP32 12-bit ADC full scale
RAIN_COVER_FRACTION = 0.5     # rain must refill at least this share of the deficit


def water_status(dr, taw, crop_p, stress_tolerance, etc_mm_day):
    """Stress thresholds and how long the crop can go without water."""
    etc = max(etc_mm_day, 0.1)
    p = adjusted_p(crop_p, etc)
    raw = p * taw
    safe_limit = raw + stress_tolerance * (taw - raw)
    return {
        "p_adjusted": round(p, 3),
        "raw_mm": round(raw, 2),
        "safe_wait_limit_mm": round(safe_limit, 2),
        "hours_to_stress": round(min(max(0.0, raw - dr) / etc * 24, MAX_WAIT_HOURS), 1),
        "hours_safe_wait": round(min(max(0.0, safe_limit - dr) / etc * 24, MAX_WAIT_HOURS), 1),
    }


def model_features(dr, taw, crop, stage_index, kc, et0, tmax, humidity, raining_now,
                   forecast_available, rain_24, rain_48, hours_until_rain, month):
    """The exact feature set the AI model sees - shared by training and live use."""
    etc = et0 * kc
    ws = water_status(dr, taw, crop["p"], crop["stress_tolerance"], etc)
    return {
        "depletion_pct": round(100 * dr / taw, 1) if taw else 0.0,
        "depletion_vs_raw_pct": round(100 * dr / ws["raw_mm"], 1) if ws["raw_mm"] else 0.0,
        "hours_crop_can_wait": ws["hours_safe_wait"],
        "taw_mm": round(taw, 2),
        "etc_mm_day": round(etc, 2),
        "et0_mm": round(et0, 2),
        "kc": round(kc, 3),
        "stage_index": stage_index,
        "crop_p": crop["p"],
        "stress_tolerance": crop["stress_tolerance"],
        "tmax_c": round(tmax, 1),
        "humidity_pct": round(humidity, 1),
        "raining_now": 1 if raining_now else 0,
        "forecast_available": 1 if forecast_available else 0,
        "forecast_rain_24h_mm": round(rain_24, 2) if forecast_available else 0.0,
        "forecast_rain_48h_mm": round(rain_48, 2) if forecast_available else 0.0,
        "hours_until_rain": (NO_RAIN_HOURS if hours_until_rain is None else round(hours_until_rain, 1))
        if forecast_available else NO_RAIN_HOURS,
        "month": month,
    }


def build_state(reading, config, weather, et0_mm, now_local, sensor_summary):
    """Assemble every number the live decision depends on."""
    crop = resolve_crop(config)
    stage = growth_stage(crop, config["sowing_date"], now_local.date())
    etc = et0_mm * stage["kc"]
    zone = root_zone(config, crop, etc)
    fc, wp, zr = zone["field_capacity_pct"], zone["wilting_point_pct"], zone["root_depth_mm"]

    soil = reading.get("soil_moisture_pct")
    dr = depletion_mm(soil, fc, wp, zr) if soil is not None else 0.0

    usable = bool(weather.get("available") and weather.get("reliability") in ("fresh", "usable"))
    today = weather["days"][0] if usable and weather.get("days") else {}
    tmax = today.get("tmax") if today.get("tmax") is not None else sensor_summary["tmax"]
    humidity = today.get("humidity") if today.get("humidity") is not None else sensor_summary["humidity"]
    wetness = reading.get("rain_wetness_pct") or 0.0

    features = model_features(
        dr, zone["taw_mm"], crop, stage["stage_index"], stage["kc"], et0_mm,
        tmax if tmax is not None else 30.0,
        humidity if humidity is not None else 60.0,
        wetness >= RAIN_NOW_WETNESS_PCT, usable,
        weather.get("rain_next_24h_mm", 0.0), weather.get("rain_next_48h_mm", 0.0),
        weather.get("hours_until_rain"), now_local.month,
    )
    ws = water_status(dr, zone["taw_mm"], crop["p"], crop["stress_tolerance"], etc)

    return {
        **features,
        "crop": config["crop"],
        "crop_name": crop["name"],
        "stage": stage["stage"],
        "days_after_sowing": stage["days_after_sowing"],
        "soil_moisture_pct": soil,
        "field_capacity_pct": fc,
        "wilting_point_pct": wp,
        "root_depth_mm": zr,
        "depletion_mm": round(dr, 2),
        "preferred_moisture_min_pct": zone["preferred_moisture_min_pct"],
        "preferred_moisture_max_pct": zone["preferred_moisture_max_pct"],
        "rain_sensor_wetness": wetness,
        "rain_probability_pct": weather.get("rain_probability_24h", 0) if usable else 0,
        **ws,
    }


def effective_rain(state):
    expected = state["forecast_rain_48h_mm"] * state["rain_probability_pct"] / 100.0
    eff = RAIN_EFFICIENCY * expected
    return eff if eff >= MIN_EFFECTIVE_RAIN_MM else 0.0


def check_inputs(reading, now, sensor_checks=True):
    """
    Minimum data-trust gate. Full anomaly detection plugs in here later.
    Returns message codes ({"key", "params"}) so the dashboard can translate them.
    """
    problems = []
    soil = reading.get("soil_moisture_pct")
    raw = reading.get("soil_raw_adc")
    if sensor_checks and raw is not None and (raw >= SOIL_ADC_MAX - 5 or raw <= 5):
        # A capacitive probe never reads the very ends of the ESP32's 12-bit ADC:
        # this is a loose wire, wrong pin or a signal above 3.3 V, not dry/wet soil
        problems.append({"key": "trust.soil_adc_limit", "params": {"raw": raw}})
    elif soil is None:
        problems.append({"key": "trust.soil_missing", "params": {}})
    elif sensor_checks and not 0 <= soil <= 100:
        problems.append({"key": "trust.soil_range", "params": {"value": soil}})

    ts = reading.get("timestamp")
    if ts is None:
        problems.append({"key": "trust.no_timestamp", "params": {}})
    else:
        age_min = (now - ts).total_seconds() / 60
        if age_min > MAX_READING_AGE_MIN:
            problems.append({"key": "trust.stale",
                             "params": {"age": round(age_min), "limit": MAX_READING_AGE_MIN}})
    return problems


def rule_decision(state, rain_probability_threshold=60, rain_cover_fraction=RAIN_COVER_FRACTION):
    """
    Forecast-trusting baseline rule (what a non-learning system would do).

    * Below RAW depletion the crop is unstressed -> no irrigation.
    * Beyond RAW it waits only if the forecast says enough rain arrives before
      the crop leaves its safe-wait zone; otherwise it irrigates.
    """
    dr, raw = state["depletion_mm"], state["raw_mm"]
    safe_limit, etc = state["safe_wait_limit_mm"], state["etc_mm_day"]
    eff_rain = effective_rain(state)
    out = {
        "effective_rain_mm": round(eff_rain, 2),
        "net_requirement_24h_mm": round(max(0.0, dr + etc - eff_rain), 2),  # eq. 2
    }

    if dr < raw:
        return {**out, "action": "NO_IRRIGATION",
                "reasons": [f"Root zone has used {dr:.1f} mm of {raw:.1f} mm readily available water.",
                            f"At {etc:.1f} mm/day crop demand, stress begins in about {state['hours_to_stress']:.0f} h."]}

    if state["raining_now"] and dr < safe_limit:
        return {**out, "action": "WAIT_FOR_RAIN",
                "reasons": ["Rain sensor shows it is raining now.",
                            f"Crop can safely wait {state['hours_safe_wait']:.0f} h."]}

    hours_wait = state["hours_safe_wait"]
    rain_reasons = []
    if not state["forecast_available"]:
        rain_reasons.append("Weather forecast is unavailable or stale, so rain is not counted on.")
    elif state["hours_until_rain"] >= NO_RAIN_HOURS:
        rain_reasons.append("No meaningful rain is forecast in the next 48 h.")
    elif state["rain_probability_pct"] < rain_probability_threshold:
        rain_reasons.append(f"Rain probability {state['rain_probability_pct']}% is below the {rain_probability_threshold}% wait threshold.")
    elif state["hours_until_rain"] > hours_wait:
        rain_reasons.append(f"Rain expected in {state['hours_until_rain']:.0f} h, but the crop can only wait {hours_wait:.0f} h.")
    elif eff_rain < rain_cover_fraction * dr:
        rain_reasons.append(f"Expected effective rain {eff_rain:.1f} mm covers too little of the {dr:.1f} mm deficit.")
    else:
        return {**out, "action": "WAIT_FOR_RAIN",
                "reasons": [f"{eff_rain:.1f} mm effective rain expected in {state['hours_until_rain']:.0f} h "
                            f"({state['rain_probability_pct']}% chance); crop can safely wait {hours_wait:.0f} h."]}

    return {**out, "action": "IRRIGATE",
            "reasons": [f"Root zone has used {dr:.1f} mm, beyond the {raw:.1f} mm the "
                        f"{state['crop_name'].lower()} tolerates at the {state['stage']} stage."] + rain_reasons}


def hindsight_label(dr, raw, safe_limit, etc_hourly, rain_hourly, cover=RAIN_COVER_FRACTION):
    """
    The correct action at a moment, judged from what really happened next.

    etc_hourly / rain_hourly: actual crop water use and rainfall (mm) for each
    following hour (48 h). Waiting was right only if real rain refilled enough
    of the deficit before the crop passed its safe-wait limit.
    """
    if dr < raw:
        return "NO_IRRIGATION"
    target = dr * (1 - cover)
    d = dr
    for etc_h, rain_h in zip(etc_hourly, rain_hourly):
        d = max(0.0, d + etc_h - RAIN_EFFICIENCY * rain_h)
        if d > safe_limit:
            return "IRRIGATE"
        if d <= target:
            return "WAIT_FOR_RAIN"
    return "IRRIGATE"


def final_decision(state, model_action, probabilities):
    """
    The AI model decides; agronomic guards keep it inside safe bounds.
    Returns (action, decided_by, guard message key or None).
    """
    if state["depletion_mm"] < state["raw_mm"]:
        note = None if model_action == "NO_IRRIGATION" else "guard.no_irrigation"
        return "NO_IRRIGATION", "model" if note is None else "guard", note

    if state["hours_safe_wait"] <= 0:
        note = None if model_action == "IRRIGATE" else "guard.must_irrigate"
        return "IRRIGATE", "model" if note is None else "guard", note

    # Crop needs water and could wait: the model chooses between waiting and irrigating
    if model_action in ("IRRIGATE", "WAIT_FOR_RAIN"):
        return model_action, "model", None
    choice = "WAIT_FOR_RAIN" if probabilities.get("WAIT_FOR_RAIN", 0) > probabilities.get("IRRIGATE", 0) else "IRRIGATE"
    return choice, "guard", "guard.no_skip"


def pump_plan(irrigation_mm, config):
    """Convert a refill depth into water volume and pump run time for the pot."""
    area_cm2 = float(config.get("pot_area_cm2", 700))
    flow = float(config.get("pump_flow_ml_per_min", 1200))
    max_s = float(config.get("max_pump_seconds", 300))
    volume_ml = irrigation_mm * area_cm2 * 0.1  # 1 mm over 1 cm^2 = 0.1 ml
    seconds = min(max_s, volume_ml / flow * 60) if flow > 0 else 0
    return {"volume_ml": round(volume_ml), "pump_seconds": round(seconds)}

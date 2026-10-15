"""
Training data from real history (synopsis 1.4: "historical weather forecast and
actual rainfall for the previous monsoon seasons").

For several Indian locations it downloads, from Open-Meteo:
  * actual hourly rainfall and daily ET0 / Tmax / humidity (ERA5 reanalysis)
  * the forecasts that were really issued 1 and 2 days ahead (Previous Runs API,
    available from March 2024)

Crop seasons are then replayed hour by hour with a daily soil-water balance.
At each decision point the model only sees what was known then (soil state,
crop, today's weather, the forecast as issued). The label is what was actually
right, judged from the real rain that followed (water_balance.hindsight_label).

Soil moisture itself is simulated by the water balance - no public dataset
measures the root zone of these crops. Real farm decisions (farm_data.py) are
added on top during training.
"""

import json
import os
import random
from datetime import date, timedelta

import numpy as np
import requests

from crops import CROPS, SOILS, stage_at
from water_balance import (
    NO_RAIN_HOURS,
    RAIN_EFFICIENCY,
    hindsight_label,
    model_features,
    rule_decision,
    water_status,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "history")
HISTORY_START = "2024-03-01"   # first full month of archived forecasts
RAIN_HOUR_MM = 0.5
RAINING_NOW_MM = 0.2

# Different climates so the model does not just memorise Pune's weather
LOCATIONS = {
    "pune": (18.6517, 73.7616),
    "nagpur": (21.1458, 79.0882),
    "jaipur": (26.9124, 75.7873),
    "chennai": (13.0827, 80.2707),
    "delhi": (28.6139, 77.2090),
    "bengaluru": (12.9716, 77.5946),
    "kolkata": (22.5726, 88.3639),
    "ahmedabad": (23.0225, 72.5714),
}


# ---------------------------------------------------------------- download

def download_location(name, lat, lon, end_date, refresh=False):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if os.path.exists(path) and not refresh:
        with open(path) as f:
            return json.load(f)

    common = {"latitude": lat, "longitude": lon, "start_date": HISTORY_START,
              "end_date": end_date, "timezone": "auto"}
    actual = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
        **common,
        "hourly": "precipitation",
        "daily": "et0_fao_evapotranspiration,temperature_2m_max,relative_humidity_2m_mean",
    }, timeout=120)
    actual.raise_for_status()
    issued = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", params={
        **common,
        "hourly": "precipitation_previous_day1,precipitation_previous_day2",
    }, timeout=120)
    issued.raise_for_status()

    a, f = actual.json(), issued.json()
    if a["hourly"]["time"] != f["hourly"]["time"]:
        raise ValueError(f"{name}: actual and forecast hours do not line up")

    data = {
        "name": name, "latitude": lat, "longitude": lon,
        "hours": a["hourly"]["time"],
        "rain": a["hourly"]["precipitation"],
        "fc_day1": f["hourly"]["precipitation_previous_day1"],
        "fc_day2": f["hourly"]["precipitation_previous_day2"],
        "days": a["daily"]["time"],
        "et0": a["daily"]["et0_fao_evapotranspiration"],
        "tmax": a["daily"]["temperature_2m_max"],
        "humidity": a["daily"]["relative_humidity_2m_mean"],
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w") as f_out:
        json.dump(data, f_out)
    return data


def download_all(refresh=False):
    end = (date.today() - timedelta(days=3)).isoformat()
    out = {}
    for name, (lat, lon) in LOCATIONS.items():
        out[name] = download_location(name, lat, lon, end, refresh)
        print(f"  {name}: {len(out[name]['days'])} days")
    return out


# ---------------------------------------------------------------- crops / soils

def random_crop(rng):
    """Synthetic crop spanning the FAO-56 parameter space, so unseen crops generalise."""
    kc_ini = rng.uniform(0.2, 1.05)
    kc_mid = rng.uniform(max(0.7, kc_ini), 1.3)
    p = rng.uniform(0.1, 0.8)
    return {
        "name": "Synthetic crop",
        "kc_ini": kc_ini, "kc_mid": kc_mid, "kc_end": rng.uniform(0.2, kc_mid),
        "stage_days": [rng.randint(10, 60), rng.randint(15, 70), rng.randint(15, 120), rng.randint(5, 60)],
        "p": round(p, 2),
        "stress_tolerance": round(min(0.6, rng.uniform(0.4, 1.0) * p), 2),
    }


def random_soil(rng):
    if rng.random() < 0.5:
        s = SOILS[rng.choice(list(SOILS))]
        return s["fc"], s["wp"]
    fc = rng.uniform(10, 45)
    return fc, rng.uniform(max(3.0, 0.25 * fc), 0.65 * fc)


# ---------------------------------------------------------------- replay

def _forecast_window(fc1, fc2, t):
    """Rain forecast as issued before hour t: next 24 h (1-day-ahead run), 24-48 h (2-day-ahead run)."""
    first = fc1[t + 1:t + 25]
    second = fc2[t + 25:t + 49]
    if len(first) < 24 or len(second) < 24 or None in first or None in second:
        return None
    hourly = first + second
    hours_until = next((k for k, mm in enumerate(hourly) if mm >= RAIN_HOUR_MM), None)
    return sum(first), sum(hourly), hours_until


def replay_location(data, rng, n_seasons):
    rain, fc1, fc2 = data["rain"], data["fc_day1"], data["fc_day2"]
    et0s, tmaxs, hums, days = data["et0"], data["tmax"], data["humidity"], data["days"]
    n_days = len(days)
    rows = []

    for _ in range(n_seasons):
        crop = CROPS[rng.choice(list(CROPS))] if rng.random() < 0.5 else random_crop(rng)
        fc, wp = random_soil(rng)
        zr = rng.choice([150, 200, 250, 300, 400, 600, 1000])
        taw = (fc - wp) / 100 * zr
        season = sum(crop["stage_days"])
        sow = rng.randrange(0, max(1, n_days - 30))

        dr = rng.uniform(0, 0.3) * taw
        # Behaviour policy: irrigate at a random point between RAW and wilting,
        # so the replay visits comfortable, stressed and badly stressed states
        trigger_into_band = rng.uniform(0.0, 0.9)
        refill_to = rng.uniform(0.0, 0.25) * taw

        for das in range(season):
            d = sow + das
            if d >= n_days - 3:
                break
            if None in (et0s[d], tmaxs[d], hums[d]):
                continue
            stage = stage_at(crop, das)
            kc = stage["kc"]
            etc = et0s[d] * kc
            h = rng.randrange(24)
            t = d * 24 + h
            day_rain = [r or 0.0 for r in rain[d * 24:d * 24 + 24]]

            dr_h = min(taw, max(0.0, dr + etc * h / 24 - RAIN_EFFICIENCY * sum(day_rain[:h + 1])))
            window = _forecast_window(fc1, fc2, t)
            future_rain = rain[t + 1:t + 49]

            if window is not None and len(future_rain) == 48 and None not in future_rain:
                rain_24, rain_48, hours_until = window
                available = rng.random() > 0.1   # sometimes the forecast is offline
                feats = model_features(
                    dr_h, taw, crop, stage["stage_index"], kc, et0s[d], tmaxs[d], hums[d],
                    (rain[t] or 0.0) >= RAINING_NOW_MM, available,
                    rain_24, rain_48, hours_until, int(days[d][5:7]),
                )
                ws = water_status(dr_h, taw, crop["p"], crop["stress_tolerance"], etc)
                etc_hourly = [et0s[min((t + k) // 24, n_days - 1)] * kc / 24 for k in range(1, 49)]
                label = hindsight_label(dr_h, ws["raw_mm"], ws["safe_wait_limit_mm"], etc_hourly, future_rain)

                # What a forecast-trusting rule would have done (baseline for evaluation)
                rule_state = {**feats, **ws, "depletion_mm": dr_h, "crop_name": crop["name"],
                              "stage": stage["stage"], "rain_probability_pct": 100}
                # Descriptive extras for the downloadable training sheet (do not affect training)
                info = {
                    "date": days[d], "hour": h, "crop": crop["name"], "stage": stage["stage"],
                    "actual_rain_48h_mm": round(sum(future_rain), 2),
                }
                rows.append((feats, label, rule_decision(rule_state)["action"], data["name"], info))

            # Advance the soil-water balance to the next day
            if dr_h >= ws_trigger(dr_h, taw, crop, etc, trigger_into_band):
                after = sum(day_rain[h + 1:])
                dr = refill_to + etc * (24 - h) / 24 - RAIN_EFFICIENCY * after
            else:
                dr = dr + etc - RAIN_EFFICIENCY * sum(day_rain)
            dr = min(taw, max(0.0, dr))
    return rows


def ws_trigger(dr, taw, crop, etc, into_band):
    ws = water_status(dr, taw, crop["p"], crop["stress_tolerance"], etc)
    return ws["raw_mm"] + into_band * (taw - ws["raw_mm"])


def build_dataset(seasons_per_location=250, seed=7, refresh=False):
    print("Downloading / loading real weather history...")
    history = download_all(refresh)
    rng = random.Random(seed)
    rows = []
    for name, data in history.items():
        loc_rows = replay_location(data, rng, seasons_per_location)
        print(f"  {name}: {len(loc_rows)} decision points")
        rows.extend(loc_rows)
    return rows


def to_arrays(rows, feature_keys):
    X = np.array([[float(r[0][k]) for k in feature_keys] for r in rows])
    y = np.array([r[1] for r in rows])
    baseline = np.array([r[2] for r in rows])
    groups = np.array([r[3] for r in rows])
    return X, y, baseline, groups


__all__ = ["build_dataset", "to_arrays", "LOCATIONS", "NO_RAIN_HOURS"]

"""
Step 2 - Weather awareness.

Fetches the farm forecast from Open-Meteo (free, no API key), summarises the
parts irrigation cares about (rain in the next 24/48 h, when it starts, ET0),
and grades how much the forecast can be trusted based on its age.

When the forecast is unavailable, ET0 falls back to the Hargreaves equation
using the farm's own DHT11 temperature history.
"""

import math
from datetime import datetime, timedelta, timezone

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Forecast age thresholds (hours)
FRESH_HOURS = 3
USABLE_HOURS = 12

RAIN_HOUR_MM = 0.5  # an hour with at least this much rain counts as "rain starts"


def fetch_forecast(latitude, longitude, timeout=10):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "precipitation,precipitation_probability,temperature_2m,relative_humidity_2m",
        "daily": (
            "et0_fao_evapotranspiration,precipitation_sum,"
            "precipitation_probability_max,temperature_2m_max,temperature_2m_min,"
            "relative_humidity_2m_mean"
        ),
        "timezone": "auto",  # daily buckets follow the farm's local day
        "forecast_days": 4,
    }
    response = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _parse_local(text, offset):
    """Open-Meteo local time string -> aware UTC datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc) - offset


def summarise(raw, fetched_at, now=None):
    """Reduce an Open-Meteo response to the irrigation-relevant numbers."""
    now = now or datetime.now(timezone.utc)
    hourly = raw["hourly"]
    daily = raw["daily"]
    offset = timedelta(seconds=raw.get("utc_offset_seconds", 0))
    local_today = (now + offset).date().isoformat()

    rain_24 = rain_48 = 0.0
    prob_24 = 0
    hours_until_rain = None
    upcoming = []

    for t, mm, prob in zip(
        hourly["time"], hourly["precipitation"], hourly["precipitation_probability"]
    ):
        hours_ahead = (_parse_local(t, offset) - now).total_seconds() / 3600
        if hours_ahead < -1 or hours_ahead > 48:
            continue
        mm = mm or 0.0
        prob = prob or 0
        rain_48 += mm
        if hours_ahead <= 24:
            rain_24 += mm
            prob_24 = max(prob_24, prob)
        if hours_until_rain is None and mm >= RAIN_HOUR_MM:
            hours_until_rain = max(0.0, hours_ahead)
        upcoming.append({"time": t, "rain_mm": mm, "probability": prob})

    age_hours = (now - fetched_at).total_seconds() / 3600
    if age_hours <= FRESH_HOURS:
        reliability = "fresh"
    elif age_hours <= USABLE_HOURS:
        reliability = "usable"
    else:
        reliability = "stale"

    days = [
        {
            "date": daily["time"][i],
            "et0_mm": daily["et0_fao_evapotranspiration"][i],
            "rain_mm": daily["precipitation_sum"][i],
            "rain_probability": daily["precipitation_probability_max"][i],
            "tmax": daily["temperature_2m_max"][i],
            "tmin": daily["temperature_2m_min"][i],
            "humidity": (daily.get("relative_humidity_2m_mean") or [None] * len(daily["time"]))[i],
        }
        for i in range(len(daily["time"]))
        if daily["time"][i] >= local_today
    ]

    return {
        "available": True,
        "source": "open-meteo",
        "fetched_at": fetched_at.isoformat(),
        "age_hours": round(age_hours, 2),
        "reliability": reliability,
        "rain_next_24h_mm": round(rain_24, 2),
        "rain_next_48h_mm": round(rain_48, 2),
        "rain_probability_24h": prob_24,
        "hours_until_rain": None if hours_until_rain is None else round(hours_until_rain, 1),
        "et0_today_mm": days[0]["et0_mm"] if days else None,
        "timezone": raw.get("timezone"),
        "utc_offset_seconds": raw.get("utc_offset_seconds", 0),
        "days": days,
        "hourly_next_48h": upcoming,
    }


def unavailable(reason):
    return {
        "available": False,
        "source": None,
        "reliability": "unavailable",
        "reason": reason,
        "rain_next_24h_mm": 0.0,
        "rain_next_48h_mm": 0.0,
        "rain_probability_24h": 0,
        "hours_until_rain": None,
        "et0_today_mm": None,
        "days": [],
        "hourly_next_48h": [],
    }


def extraterrestrial_radiation_mm(latitude, day_of_year):
    """Ra in mm/day of evaporation equivalent (FAO-56 eq. 21, x0.408)."""
    phi = math.radians(latitude)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    ra_mj = (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta)
        + math.cos(phi) * math.cos(delta) * math.sin(ws)
    )
    return 0.408 * ra_mj


def hargreaves_et0(tmax, tmin, latitude, day_of_year):
    """FAO-56 eq. 52 - needs only daily max/min temperature."""
    tmean = (tmax + tmin) / 2
    ra = extraterrestrial_radiation_mm(latitude, day_of_year)
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(max(0.0, tmax - tmin)) * ra)


DEFAULT_ET0_MM = 4.0  # typical Pune value; used only when nothing else is available


def resolve_et0(weather, sensor_temps, latitude, day_of_year):
    """Pick the best available ET0: forecast -> Hargreaves(sensor) -> default."""
    if weather.get("available") and weather.get("reliability") != "stale" and weather.get("et0_today_mm") is not None:
        return weather["et0_today_mm"], "forecast (Open-Meteo FAO-56)"

    temps = [t for t in sensor_temps if t is not None]
    if len(temps) >= 6 and max(temps) - min(temps) >= 2:
        return round(hargreaves_et0(max(temps), min(temps), latitude, day_of_year), 2), "Hargreaves (farm sensor, last 24 h)"

    return DEFAULT_ET0_MM, "default (no forecast or sensor history)"

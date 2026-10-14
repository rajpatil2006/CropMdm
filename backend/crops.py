"""
Step 1 - Crop awareness.

Crop and soil reference data (FAO Irrigation & Drainage Paper 56) and helpers
that turn a crop + sowing date + soil into:
  * the current growth stage and crop coefficient Kc
  * the root-zone water capacity (TAW) and readily available water (RAW)
  * the preferred soil-moisture band for that crop right now

Any crop works: pick one from the FAO-56 table below, or configure a custom
crop with its own Kc values, stage lengths and depletion fraction p.
"""

from datetime import date

STAGES = ["initial", "development", "mid", "late"]


def _crop(name, kc_ini, kc_mid, kc_end, stage_days, p, stress_tolerance=None):
    return {
        "name": name,
        "kc_ini": kc_ini, "kc_mid": kc_mid, "kc_end": kc_end,
        "stage_days": stage_days,
        "p": p,
        "stress_tolerance": stress_tolerance if stress_tolerance is not None else default_tolerance(p),
    }


def default_tolerance(p):
    """
    Share of the (TAW - RAW) band a crop may enter while waiting for forecast
    rain. FAO-56 has no such value; it is scaled from p (drought-tolerant crops
    can wait longer). Override per crop when field experience says otherwise.
    """
    return round(0.7 * p, 2)


# Kc: FAO-56 Table 12. stage_days (initial, development, mid, late): FAO-56
# Table 11, one typical region each - adjust to local practice.
# p: FAO-56 Table 22 depletion fraction before stress (lower = more sensitive).
CROPS = {
    # vegetables
    "tomato": _crop("Tomato", 0.60, 1.15, 0.80, [30, 40, 45, 30], 0.40, 0.25),
    "chilli": _crop("Chilli / Pepper", 0.60, 1.05, 0.90, [25, 35, 40, 20], 0.30, 0.20),
    "spinach": _crop("Spinach", 0.70, 1.00, 0.95, [20, 20, 15, 5], 0.20, 0.10),
    "eggplant": _crop("Eggplant / Brinjal", 0.60, 1.05, 0.90, [30, 40, 40, 20], 0.45),
    "cabbage": _crop("Cabbage", 0.70, 1.05, 0.95, [40, 60, 50, 15], 0.45),
    "cauliflower": _crop("Cauliflower", 0.70, 1.05, 0.95, [35, 50, 40, 15], 0.45),
    "broccoli": _crop("Broccoli", 0.70, 1.05, 0.95, [35, 45, 40, 15], 0.45),
    "lettuce": _crop("Lettuce", 0.70, 1.00, 0.95, [20, 30, 15, 10], 0.30),
    "carrot": _crop("Carrot", 0.70, 1.05, 0.95, [20, 30, 50, 20], 0.35),
    "radish": _crop("Radish", 0.70, 0.90, 0.85, [5, 10, 15, 5], 0.30),
    "onion": _crop("Onion (dry)", 0.70, 1.05, 0.75, [15, 25, 70, 40], 0.30),
    "potato": _crop("Potato", 0.50, 1.15, 0.75, [25, 30, 45, 30], 0.35),
    "sweet_potato": _crop("Sweet potato", 0.50, 1.15, 0.65, [20, 30, 60, 40], 0.65),
    "cucumber": _crop("Cucumber", 0.60, 1.00, 0.75, [20, 30, 40, 15], 0.50),
    "pumpkin": _crop("Pumpkin / Squash", 0.50, 1.00, 0.80, [20, 30, 30, 20], 0.35),
    "watermelon": _crop("Watermelon", 0.40, 1.00, 0.75, [20, 30, 30, 30], 0.40),
    "melon": _crop("Melon", 0.50, 0.85, 0.60, [25, 35, 40, 20], 0.40),
    "green_bean": _crop("Green bean", 0.50, 1.05, 0.90, [20, 30, 30, 10], 0.45),
    "pea": _crop("Pea (fresh)", 0.50, 1.15, 1.10, [15, 25, 35, 15], 0.35),
    "sweet_corn": _crop("Sweet corn", 0.30, 1.15, 1.05, [20, 20, 30, 10], 0.50),
    "strawberry": _crop("Strawberry", 0.40, 0.85, 0.75, [20, 30, 40, 30], 0.20),
    # pulses and oilseeds
    "dry_bean": _crop("Bean (dry)", 0.40, 1.15, 0.35, [20, 30, 40, 20], 0.45),
    "chickpea": _crop("Chickpea", 0.40, 1.00, 0.35, [25, 25, 35, 20], 0.50),
    "lentil": _crop("Lentil", 0.40, 1.10, 0.30, [20, 30, 60, 40], 0.50),
    "soybean": _crop("Soybean", 0.40, 1.15, 0.50, [20, 30, 60, 25], 0.50),
    "groundnut": _crop("Groundnut", 0.40, 1.15, 0.60, [25, 35, 45, 25], 0.50),
    "sunflower": _crop("Sunflower", 0.35, 1.05, 0.35, [25, 35, 45, 25], 0.45),
    "mustard": _crop("Mustard / Rapeseed", 0.35, 1.05, 0.35, [25, 35, 55, 30], 0.60),
    "sesame": _crop("Sesame", 0.35, 1.10, 0.25, [20, 30, 40, 20], 0.60),
    "castor": _crop("Castor", 0.35, 1.15, 0.55, [25, 40, 65, 50], 0.50),
    "cotton": _crop("Cotton", 0.35, 1.18, 0.60, [30, 50, 60, 55], 0.65),
    # cereals and others
    "wheat": _crop("Wheat", 0.30, 1.15, 0.35, [15, 25, 50, 30], 0.55, 0.40),
    "barley": _crop("Barley", 0.30, 1.15, 0.25, [15, 25, 50, 30], 0.55),
    "maize": _crop("Maize", 0.30, 1.20, 0.35, [20, 35, 40, 30], 0.55, 0.40),
    "sorghum": _crop("Sorghum", 0.30, 1.05, 0.55, [20, 35, 40, 30], 0.55),
    "millet": _crop("Millet", 0.30, 1.00, 0.30, [15, 25, 40, 25], 0.55),
    "rice": _crop("Rice (non-flooded)", 1.05, 1.20, 0.75, [30, 30, 60, 30], 0.20),
    "sugarcane": _crop("Sugarcane", 0.40, 1.25, 0.75, [35, 60, 190, 120], 0.65),
    "banana": _crop("Banana (1st year)", 0.50, 1.10, 1.00, [120, 90, 120, 60], 0.35),
    "grape": _crop("Grape", 0.30, 0.85, 0.45, [20, 40, 120, 60], 0.35),
}

# Volumetric water content (%) at field capacity / wilting point,
# mid-points of FAO-56 Table 19. "potting_mix" is a typical peat/compost mix.
SOILS = {
    "sand": {"name": "Sand", "fc": 12.0, "wp": 4.5},
    "sandy_loam": {"name": "Sandy loam", "fc": 23.0, "wp": 11.0},
    "loam": {"name": "Loam", "fc": 25.0, "wp": 12.0},
    "silt_loam": {"name": "Silt loam", "fc": 29.0, "wp": 15.0},
    "clay": {"name": "Clay", "fc": 36.0, "wp": 22.0},
    "potting_mix": {"name": "Potting mix", "fc": 40.0, "wp": 12.0},
}


def resolve_crop(config):
    """Crop parameters for a config: the FAO-56 table entry or the custom crop."""
    if config["crop"] == "custom":
        c = config["custom_crop"]
        return _crop(c.get("name") or "Custom crop", c["kc_ini"], c["kc_mid"], c["kc_end"],
                     list(c["stage_days"]), c["p"], c.get("stress_tolerance"))
    return CROPS[config["crop"]]


def growth_stage(crop, sowing_date, today=None):
    """Return days after sowing, stage name/index and Kc (FAO-56 eq. 66 interpolation)."""
    today = today or date.today()
    return stage_at(crop, max(0, (today - sowing_date).days))


def stage_at(crop, das):
    ini, dev, mid, late = crop["stage_days"]
    kc_ini, kc_mid, kc_end = crop["kc_ini"], crop["kc_mid"], crop["kc_end"]
    season = ini + dev + mid + late

    if das < ini:
        index, kc, into = 0, kc_ini, das
    elif das < ini + dev:
        into = das - ini
        index, kc = 1, kc_ini + (kc_mid - kc_ini) * into / dev
    elif das < ini + dev + mid:
        into = das - ini - dev
        index, kc = 2, kc_mid
    elif das < season:
        into = das - ini - dev - mid
        index, kc = 3, kc_mid + (kc_end - kc_mid) * into / late
    else:
        index, kc, into = 3, kc_end, late

    return {
        "days_after_sowing": das,
        "stage_index": index,
        "stage": STAGES[index],
        "day_in_stage": into,
        "stage_length_days": crop["stage_days"][index],
        "season_length_days": season,
        "season_complete": das >= season,
        "kc": round(kc, 3),
    }


def adjusted_p(p_table, etc_mm_day):
    """FAO-56 p adjustment: crops tolerate less depletion on high-ET days."""
    return min(0.8, max(0.1, p_table + 0.04 * (5.0 - etc_mm_day)))


def soil_limits(config):
    """Field capacity / wilting point in the soil sensor's % units."""
    soil = SOILS[config.get("soil_type", "loam")]
    fc = config.get("field_capacity_pct") or soil["fc"]
    wp = config.get("wilting_point_pct") or soil["wp"]
    return float(fc), float(wp)


def root_zone(config, crop, etc_mm_day):
    """TAW, RAW (mm) and the preferred moisture band for the configured crop."""
    fc, wp = soil_limits(config)
    zr = float(config.get("root_depth_mm", 200))

    taw = (fc - wp) / 100.0 * zr
    p = adjusted_p(crop["p"], etc_mm_day)
    raw = p * taw

    # Soil moisture at which RAW is used up = the bottom of the comfort band.
    lower = fc - p * (fc - wp)

    return {
        "field_capacity_pct": fc,
        "wilting_point_pct": wp,
        "root_depth_mm": zr,
        "taw_mm": round(taw, 2),
        "raw_mm": round(raw, 2),
        "p": round(p, 3),
        "preferred_moisture_min_pct": round(lower, 1),
        "preferred_moisture_max_pct": round(fc, 1),
    }


def depletion_mm(soil_moisture_pct, fc, wp, root_depth_mm):
    """Root-zone depletion Dr (mm below field capacity), clipped to [0, TAW]."""
    theta = min(max(soil_moisture_pct, wp), fc)
    return (fc - theta) / 100.0 * root_depth_mm


def catalogue():
    return {
        "crops": [
            {"key": k, **{f: v[f] for f in ("name", "kc_ini", "kc_mid", "kc_end",
                                             "stage_days", "p", "stress_tolerance")}}
            for k, v in sorted(CROPS.items(), key=lambda kv: kv[1]["name"])
        ],
        "soils": [{"key": k, **v} for k, v in SOILS.items()],
        "stages": STAGES,
    }

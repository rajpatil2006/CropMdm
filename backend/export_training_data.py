"""
Write the data the AI model was trained on to an Excel workbook
(backend/models/training_data.xlsx), which admins download from the dashboard.

    python export_training_data.py      # rebuild from the cached weather history

train_model.py calls export() after every training run, so the workbook always
matches the deployed model.
"""

import json
import os
from datetime import datetime, timezone

import xlsxwriter

from water_balance import ACTION_LABELS
from xai import FEATURE_KEYS, FEATURES, META_PATH, MODEL_DIR

EXCEL_PATH = os.path.join(MODEL_DIR, "training_data.xlsx")
HOLDOUT = {"chennai", "kolkata"}

# (header, how to get the value from a row, column width)
FEATURE_COLUMNS = [(f"{label} ({unit})" if unit else label, key) for key, label, unit in FEATURES]

COLUMN_HELP = {
    "depletion_pct": "Share of the root zone's water (TAW) the crop has already used.",
    "depletion_vs_raw_pct": "Water used compared with the crop's stress limit (RAW); above 100% the crop is stressed.",
    "hours_crop_can_wait": "Hours until the crop passes its safe-wait limit at the current water use.",
    "taw_mm": "Total water the root zone can hold between field capacity and wilting point.",
    "etc_mm_day": "Crop water use per day: ETc = Kc x ET0 (FAO-56).",
    "et0_mm": "Reference evapotranspiration from the weather (FAO-56 Penman-Monteith, ERA5).",
    "kc": "FAO-56 crop coefficient for the crop's current growth stage.",
    "stage_index": "Growth stage: 0 initial, 1 development, 2 mid-season, 3 late-season.",
    "crop_p": "FAO-56 depletion fraction p: higher = crop tolerates drier soil.",
    "stress_tolerance": "Share of the stress band the crop may enter while waiting for rain.",
    "tmax_c": "Maximum air temperature of the day.",
    "humidity_pct": "Mean relative humidity of the day.",
    "raining_now": "1 if it rained in the hour before the decision.",
    "forecast_available": "0 when the forecast was deliberately hidden (10% of rows) to teach offline behaviour.",
    "forecast_rain_24h_mm": "Rain forecast for the next 24 h, as issued 1 day earlier (archived forecast).",
    "forecast_rain_48h_mm": "Rain forecast for the next 48 h, as issued 1-2 days earlier (archived forecasts).",
    "hours_until_rain": "Hours until the forecast says rain starts (72 = none forecast).",
    "month": "Calendar month (1-12).",
}


def _readme(wb, ws, meta, counts, n_rows, n_farm):
    bold = wb.add_format({"bold": True})
    title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1F8A5C"})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    head = wb.add_format({"bold": True, "bg_color": "#E0F4E9", "border": 1})
    cell = wb.add_format({"text_wrap": True, "valign": "top", "border": 1})
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 28)
    ws.set_column(2, 2, 90)
    ws.write(0, 0, "CropMind - AI irrigation model training data", title)
    lines = [
        ("Model", "Random Forest classifier (150 trees, max depth 16) with SHAP TreeExplainer explanations."),
        ("Trained at", meta.get("trained_at", "")),
        ("Rows in this workbook", f"{n_rows:,} replayed decisions + {n_farm:,} labelled farm decisions"),
        ("Weather data", "Open-Meteo historical weather (ERA5 reanalysis): hourly rainfall, daily ET0, max temperature, humidity."),
        ("Forecast data", "Open-Meteo Previous Runs API: rain forecasts as they were issued 1 and 2 days ahead (from March 2024)."),
        ("Locations", "Pune, Nagpur, Jaipur, Delhi, Bengaluru, Ahmedabad, Chennai, Kolkata (Chennai and Kolkata held out for testing)."),
        ("Crops", "40 FAO-56 crops (Allen et al., 1998) plus randomly generated crop parameters, so unseen crops generalise."),
        ("Soil moisture", "Simulated day by day with the FAO-56 root-zone water balance (no public dataset measures it)."),
        ("Label (correct action)", "Judged from what really happened: waiting was right only if the actual rain in the next 48 h "
                                   "refilled at least half of the deficit before the crop passed its safe limit; otherwise irrigate. "
                                   "No irrigation if the soil still held readily available water."),
        ("Baseline", "'Forecast-only rule' = a rule that trusts the rain forecast, for comparison."),
        ("Class counts", ", ".join(f"{ACTION_LABELS[k]}: {v:,}" for k, v in counts.items())),
        ("Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]
    for i, (k, v) in enumerate(lines, start=2):
        ws.write(i, 0, k, bold)
        ws.merge_range(i, 1, i, 2, v, wrap)
        ws.set_row(i, 30 if len(v) > 110 else 18)

    r = len(lines) + 4
    ws.write(r, 0, "Column", head)
    ws.write(r, 1, "Model feature key", head)
    ws.write(r, 2, "Meaning", head)
    extra = [
        ("City", "", "Location whose real weather was replayed."),
        ("Date / Hour", "", "Local date and hour of the decision."),
        ("Crop / Growth stage", "", "FAO-56 crop name, or 'Synthetic crop' for generated parameters."),
    ]
    rows = extra + [(header, key, COLUMN_HELP.get(key, "")) for header, key in FEATURE_COLUMNS] + [
        ("Actual rain next 48 h (mm)", "", "Rain that really fell afterwards (used only to create the label)."),
        ("Correct action (label)", "", "What the model learns to predict."),
        ("Forecast-only rule", "", "Decision of the baseline rule on the same row."),
        ("Used for", "", "'training' or 'test (held-out city)' in the published evaluation."),
    ]
    for i, (a, b, c) in enumerate(rows, start=r + 1):
        ws.write(i, 0, a, cell)
        ws.write(i, 1, b, cell)
        ws.write(i, 2, c, cell)


def _evaluation(wb, ws, meta):
    bold = wb.add_format({"bold": True})
    head = wb.add_format({"bold": True, "bg_color": "#E0F4E9", "border": 1})
    pct = wb.add_format({"num_format": "0.0%", "border": 1})
    num = wb.add_format({"num_format": "#,##0", "border": 1})
    txt = wb.add_format({"border": 1})
    ev = meta.get("evaluation", {})
    ws.set_column(0, 0, 44)
    ws.set_column(1, 2, 20)
    ws.write(0, 0, f"Held-out cities (never seen in training): {', '.join(ev.get('holdout_locations', []))}", bold)
    ws.write(2, 0, "Decisions where the crop needed water", head)
    ws.write(2, 1, "AI model", head)
    ws.write(2, 2, "Forecast-only rule", head)
    m, r = ev.get("model_rain_wait", {}), ev.get("rule_rain_wait", {})
    rows = [
        ("Correct", m.get("accuracy"), r.get("accuracy"), pct),
        ("Wrong waits (crop stressed)", m.get("wrong_wait_crop_stressed"), r.get("wrong_wait_crop_stressed"), num),
        ("Correct waits", m.get("correct_waits"), r.get("correct_waits"), num),
        ("Irrigated although rain came", m.get("unneeded_irrigation_rain_came"), r.get("unneeded_irrigation_rain_came"), num),
        ("Decisions in test set (crop needed water)", m.get("decisions_needing_water"), r.get("decisions_needing_water"), num),
    ]
    for i, (label, a, b, fmt) in enumerate(rows, start=3):
        ws.write(i, 0, label, txt)
        ws.write(i, 1, a, fmt)
        ws.write(i, 2, b, fmt)
    ws.write(9, 0, "All test decisions", head)
    ws.write(9, 1, "AI model", head)
    ws.write(9, 2, "Forecast-only rule", head)
    ws.write(10, 0, f"Overall accuracy ({ev.get('test_decisions', 0):,} decisions)", txt)
    ws.write(10, 1, ev.get("model_accuracy"), pct)
    ws.write(10, 2, ev.get("rule_accuracy"), pct)


def export(rows, farm_rows=None, meta=None, path=EXCEL_PATH):
    """rows: replay rows (feats, label, rule_action, city, info); farm_rows: (feats, label, source)."""
    farm_rows = farm_rows or []
    if meta is None:
        with open(META_PATH) as f:
            meta = json.load(f)
    counts = {k: 0 for k in ("IRRIGATE", "WAIT_FOR_RAIN", "NO_IRRIGATION")}
    for r in rows:
        counts[r[1]] += 1
    for r in farm_rows:
        counts[r[1]] = counts.get(r[1], 0) + 1

    wb = xlsxwriter.Workbook(path, {"constant_memory": True})
    _readme(wb, wb.add_worksheet("README"), meta, counts, len(rows), len(farm_rows))
    _evaluation(wb, wb.add_worksheet("Evaluation"), meta)

    head = wb.add_format({"bold": True, "bg_color": "#122B39", "font_color": "#FFFFFF", "text_wrap": True, "valign": "top"})
    ws = wb.add_worksheet("Training data")
    headers = (["City", "Date", "Hour", "Crop", "Growth stage"] + [h for h, _ in FEATURE_COLUMNS]
               + ["Actual rain next 48 h (mm)", "Correct action (label)", "Forecast-only rule", "Used for"])
    ws.set_row(0, 45)
    ws.write_row(0, 0, headers, head)
    ws.set_column(0, len(headers) - 1, 13)
    ws.freeze_panes(1, 0)
    for i, (feats, label, rule, city, info) in enumerate(rows, start=1):
        ws.write_row(i, 0, [
            city.title(), info["date"], info["hour"], info["crop"], info["stage"],
            *[feats[k] for k in FEATURE_KEYS],
            info["actual_rain_48h_mm"], ACTION_LABELS[label], ACTION_LABELS[rule],
            "test (held-out city)" if city in HOLDOUT else "training",
        ])
    ws.autofilter(0, 0, len(rows), len(headers) - 1)

    fs = wb.add_worksheet("Farm decisions")
    fs.set_row(0, 45)
    fs.write_row(0, 0, ["Source"] + [h for h, _ in FEATURE_COLUMNS] + ["Correct action (label)"], head)
    fs.set_column(0, len(FEATURE_COLUMNS) + 1, 13)
    if not farm_rows:
        fs.write(1, 0, "No labelled farm decisions were used yet. They are added when the model is retrained "
                       "after the pot trials (each counts 20x a replayed row).")
    for i, (feats, label, source) in enumerate(farm_rows, start=1):
        fs.write_row(i, 0, [source] + [feats[k] for k in FEATURE_KEYS] + [ACTION_LABELS.get(label, label)])

    wb.close()
    return path


if __name__ == "__main__":
    from replay import build_dataset

    meta_now = json.load(open(META_PATH))
    data_rows = build_dataset()
    # The deployed model used no farm rows unless its metadata says so
    out = export(data_rows, [], meta_now)
    print(f"Wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB, {len(data_rows):,} rows)")

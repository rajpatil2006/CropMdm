"""
Step 3 - AI irrigation model + SHAP explainability (synopsis sections 3.3, 3.4).

A Random Forest decides between irrigating, waiting for rain and not irrigating.
It is trained by train_model.py on real weather history (replay.py) plus
labelled decisions from this farm (farm_data.py).

Crops are described to the model only through their FAO-56 parameters
(Kc, p, stress tolerance, growth stage), never by name, so any crop with
those parameters is supported.

For every decision SHAP (TreeExplainer) reports how much each feature pushed
the model towards the chosen action, which is turned into plain sentences.
"""

import json
import os

import joblib
import numpy as np
import shap

from water_balance import ACTION_LABELS, NO_RAIN_HOURS

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "irrigation_model.joblib")
META_PATH = os.path.join(MODEL_DIR, "irrigation_model.json")

# (state key, farmer-facing name, unit)
FEATURES = [
    ("depletion_pct", "Root-zone water used", "%"),
    ("depletion_vs_raw_pct", "Water used vs stress threshold", "%"),
    ("hours_crop_can_wait", "Hours crop can safely wait", "h"),
    ("taw_mm", "Soil water capacity", "mm"),
    ("etc_mm_day", "Crop water demand (ETc)", "mm/day"),
    ("et0_mm", "Reference evapotranspiration (ET0)", "mm/day"),
    ("kc", "Crop coefficient Kc", ""),
    ("stage_index", "Growth stage", ""),
    ("crop_p", "Crop drought tolerance p", ""),
    ("stress_tolerance", "Crop rain-wait tolerance", ""),
    ("tmax_c", "Max temperature today", "°C"),
    ("humidity_pct", "Humidity today", "%"),
    ("raining_now", "Raining now", ""),
    ("forecast_available", "Forecast available", ""),
    ("forecast_rain_24h_mm", "Forecast rain (24 h)", "mm"),
    ("forecast_rain_48h_mm", "Forecast rain (48 h)", "mm"),
    ("hours_until_rain", "Hours until forecast rain", "h"),
    ("month", "Month", ""),
]
FEATURE_KEYS = [f[0] for f in FEATURES]
STAGE_NAMES = ["initial", "development", "mid-season", "late-season"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def feature_vector(state):
    return [float(state[k]) for k in FEATURE_KEYS]


class IrrigationExplainer:
    def __init__(self):
        meta = None
        if os.path.exists(META_PATH):
            with open(META_PATH) as f:
                meta = json.load(f)
        if not os.path.exists(MODEL_PATH) or meta is None or meta.get("features") != FEATURE_KEYS:
            print("No up-to-date model found - training it now (first run downloads weather history)...")
            from train_model import train
            train()
            with open(META_PATH) as f:
                meta = json.load(f)
        self.model = joblib.load(MODEL_PATH)
        self.meta = meta
        self.classes = [str(c) for c in self.model.classes_]
        self.explainer = shap.TreeExplainer(self.model)

    def predict(self, state):
        x = np.array([feature_vector(state)])
        proba = self.model.predict_proba(x)[0]
        best = self.classes[int(np.argmax(proba))]
        return best, {c: round(float(p), 4) for c, p in zip(self.classes, proba)}

    def explain(self, state, action):
        """SHAP contributions of each feature towards `action` (probability points)."""
        x = np.array([feature_vector(state)])
        exp = self.explainer(x)
        ci = self.classes.index(action)

        values = np.asarray(exp.values)
        values = values[0, :, ci] if values.ndim == 3 else values[0]
        base = np.asarray(exp.base_values)
        base = float(base[0, ci] if base.ndim == 2 else base[ci] if base.ndim == 1 else base)

        contributions = []
        for (key, label, unit), value, s in zip(FEATURES, x[0], values):
            contributions.append({
                "feature": key,
                "label": label,
                "value": round(float(value), 2),
                "display_value": _display(key, value, unit),
                "shap": round(float(s), 4),
            })
        contributions.sort(key=lambda c: abs(c["shap"]), reverse=True)

        return {
            "method": "SHAP TreeExplainer",
            "explained_action": action,
            "base_value": round(base, 4),
            "contributions": contributions,
            "summary": [_sentence(c, action) for c in contributions[:4] if abs(c["shap"]) >= 0.01],
        }


def _display(key, value, unit):
    if key == "stage_index":
        return STAGE_NAMES[int(value)]
    if key == "month":
        return MONTHS[int(value) - 1]
    if key in ("raining_now", "forecast_available"):
        return "yes" if value else "no"
    if key == "hours_until_rain" and value >= NO_RAIN_HOURS:
        return "none forecast"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text} {unit}".strip()


def _sentence(c, action):
    verb = "supports" if c["shap"] > 0 else "argues against"
    return (f"{c['label']} ({c['display_value']}) {verb} \"{ACTION_LABELS[action]}\" "
            f"({c['shap'] * 100:+.0f} pts).")

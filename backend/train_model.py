"""
Train the irrigation model on real data.

    python train_model.py              # replay history + farm labels, evaluate, save
    python train_model.py --refresh    # re-download weather history first
    python train_model.py --label-farm # first label logged farm decisions older than 48 h

Evaluation is honest about generalisation:
  * locations held out entirely (model never saw their weather)
  * compared against the forecast-trusting rule on the same decisions
The saved model is then refit on all locations + farm data.
"""

import argparse
import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from replay import build_dataset, to_arrays
from water_balance import ACTIONS
from xai import FEATURE_KEYS, META_PATH, MODEL_DIR, MODEL_PATH

HOLDOUT_LOCATIONS = ["chennai", "kolkata"]
FARM_WEIGHT = 20.0   # one real farm decision counts as much as 20 replayed ones

# WAIT_FOR_RAIN is rare (~0.3 % of decisions). Weighting it x10 was chosen on
# held-out cities: about half of "wait" calls are right, and wrong waits fall
# ~88 % vs the forecast-trusting rule. Higher weights catch more rain but stress
# the crop more often; "balanced" gave 412 wrong waits for 190 correct ones.
CLASS_WEIGHT = {"IRRIGATE": 1.0, "NO_IRRIGATION": 1.0, "WAIT_FOR_RAIN": 10.0}


def make_model(seed=42):
    return RandomForestClassifier(
        n_estimators=150, max_depth=16, min_samples_leaf=5,
        class_weight=CLASS_WEIGHT, random_state=seed, n_jobs=-1,
    )


def rain_wait_quality(y_true, y_pred):
    """On decisions where the crop needed water: how often each kind of mistake happened."""
    need = y_true != "NO_IRRIGATION"
    t, p = y_true[need], y_pred[need]
    return {
        "decisions_needing_water": int(need.sum()),
        "wrong_wait_crop_stressed": int(((p == "WAIT_FOR_RAIN") & (t == "IRRIGATE")).sum()),
        "unneeded_irrigation_rain_came": int(((p == "IRRIGATE") & (t == "WAIT_FOR_RAIN")).sum()),
        "correct_waits": int(((p == "WAIT_FOR_RAIN") & (t == "WAIT_FOR_RAIN")).sum()),
        "accuracy": round(float((t == p).mean()), 4) if len(t) else None,
    }


def load_farm(label_first):
    """Farm labels from MongoDB, if the database is reachable."""
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    from farm_data import label_farm_decisions, load_farm_rows

    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("Farm data skipped (MONGODB_URI not set)")
        return []
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000, tz_aware=True)
        db = client[os.getenv("MONGODB_DATABASE", "cropmind")]
        if label_first:
            cfg = db["farm_config"].find_one({"_id": "ESP32_FARM_01"}) or {}
            print("Labelling farm decisions:", label_farm_decisions(
                db, FEATURE_KEYS, cfg.get("latitude", 18.6517), cfg.get("longitude", 73.7616)))
        rows = load_farm_rows(db, FEATURE_KEYS)
    except PyMongoError as exc:
        print(f"Farm data skipped (database not available: {exc})")
        return []
    print(f"Farm-labelled decisions: {len(rows)}")
    return rows


def train(refresh=False, label_farm=False, use_farm=False):
    rows = build_dataset(refresh=refresh)
    X, y, baseline, groups = to_arrays(rows, FEATURE_KEYS)
    counts = {a: int((y == a).sum()) for a in ACTIONS}
    print(f"Replay decisions: {len(y)}  {counts}")

    # 1) Generalisation test on locations the model never sees
    test = np.isin(groups, HOLDOUT_LOCATIONS)
    model = make_model()
    model.fit(X[~test], y[~test])
    pred = model.predict(X[test])
    evaluation = {
        "holdout_locations": HOLDOUT_LOCATIONS,
        "test_decisions": int(test.sum()),
        "model_accuracy": round(float(accuracy_score(y[test], pred)), 4),
        "rule_accuracy": round(float(accuracy_score(y[test], baseline[test])), 4),
        "model_rain_wait": rain_wait_quality(y[test], pred),
        "rule_rain_wait": rain_wait_quality(y[test], baseline[test]),
        "confusion_matrix": {
            "labels": ACTIONS,
            "matrix": confusion_matrix(y[test], pred, labels=ACTIONS).tolist(),
        },
        "report": classification_report(y[test], pred, output_dict=True, zero_division=0),
    }
    print(f"Held-out locations {HOLDOUT_LOCATIONS}: model {evaluation['model_accuracy']:.3f} "
          f"vs forecast-trusting rule {evaluation['rule_accuracy']:.3f}")
    print("  model:", evaluation["model_rain_wait"])
    print("  rule: ", evaluation["rule_rain_wait"])

    # 2) Final model on everything, with real farm decisions weighted up
    weights = np.ones(len(y))
    farm_rows = load_farm(label_farm) if (use_farm or label_farm) else []
    if farm_rows:
        Xf = np.array([[float(r[0][k]) for k in FEATURE_KEYS] for r in farm_rows])
        yf = np.array([r[1] for r in farm_rows])
        X, y = np.vstack([X, Xf]), np.concatenate([y, yf])
        weights = np.concatenate([weights, np.full(len(yf), FARM_WEIGHT)])

    final = make_model()
    final.fit(X, y, sample_weight=weights)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(final, MODEL_PATH, compress=3)
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "trained_on": "Real weather + archived forecasts (Open-Meteo, Mar 2024 onward) for 8 Indian "
                      "locations, replayed through an FAO-56 soil-water balance for FAO-56 and "
                      "synthetic crops; labels from actual subsequent rainfall"
                      + (f"; plus {len(farm_rows)} labelled farm decisions" if farm_rows else ""),
        "replay_decisions": int(len(rows)),
        "farm_decisions": len(farm_rows),
        "class_counts": counts,
        "features": FEATURE_KEYS,
        "classes": [str(c) for c in final.classes_],
        "evaluation": evaluation,
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    # Downloadable copy of exactly this training data (admin dashboard)
    from export_training_data import export
    print("Training data workbook:", export(rows, farm_rows, meta))
    print(f"Saved model to {MODEL_PATH}")
    return final, meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="re-download weather history")
    parser.add_argument("--label-farm", action="store_true", help="label farm decisions before training")
    parser.add_argument("--no-farm", action="store_true", help="ignore farm data")
    args = parser.parse_args()
    train(refresh=args.refresh, label_farm=args.label_farm, use_farm=not args.no_farm)

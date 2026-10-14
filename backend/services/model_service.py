"""Holds the loaded AI model and runs retraining in the background."""

import logging
import threading
from datetime import datetime, timezone

from xai import IrrigationExplainer


class ModelService:
    def __init__(self):
        # Loads the saved model, or trains it on first start (downloads weather history)
        self.explainer = IrrigationExplainer()
        self._lock = threading.Lock()
        self.retrain_status = {"state": "idle"}

    def predict(self, state):
        return self.explainer.predict(state)

    def explain(self, state, action):
        return self.explainer.explain(state, action)

    @property
    def meta(self):
        return self.explainer.meta

    def start_retrain(self, label_farm=True):
        """Retrain on replayed weather history + labelled farm data, then hot-swap the model."""
        if not self._lock.acquire(blocking=False):
            return False
        self.retrain_status = {"state": "running", "started_at": datetime.now(timezone.utc).isoformat()}
        threading.Thread(target=self._retrain, args=(label_farm,), daemon=True).start()
        return True

    def _retrain(self, label_farm):
        try:
            from train_model import train
            _, meta = train(label_farm=label_farm, use_farm=True)
            self.explainer = IrrigationExplainer()
            self.retrain_status = {
                "state": "done",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "farm_decisions": meta.get("farm_decisions", 0),
                "model_accuracy": meta.get("evaluation", {}).get("model_accuracy"),
            }
        except Exception as exc:  # noqa: BLE001 - report any training failure to the admin
            logging.exception("Retraining failed")
            self.retrain_status = {"state": "failed", "error": str(exc),
                                   "finished_at": datetime.now(timezone.utc).isoformat()}
        finally:
            self._lock.release()


model_service = ModelService()

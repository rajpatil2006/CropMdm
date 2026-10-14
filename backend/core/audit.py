"""Audit log: who did what, and when."""

import logging
from datetime import datetime, timezone

from pymongo.errors import PyMongoError

from core import db


def record(actor, action, target=None, details=None):
    """actor: user document, a device id string, or "system"."""
    if isinstance(actor, dict):
        who, role = actor["_id"], actor.get("role")
    else:
        who, role = str(actor), "device" if actor != "system" else "system"
    try:
        db.audit_log.insert_one({
            "at": datetime.now(timezone.utc),
            "actor": who,
            "role": role,
            "action": action,
            "target": target,
            "details": details or {},
        })
    except PyMongoError:
        logging.exception("Could not write audit log")

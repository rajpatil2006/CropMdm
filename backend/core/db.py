"""MongoDB connection and collections shared by the whole backend."""

import os

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "cropmind")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing from the .env file")

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=10000,
    tz_aware=True,  # return UTC-aware datetimes so ages/ISO strings are correct
)
db = client[MONGODB_DATABASE]

users = db["users"]
devices = db["devices"]
readings = db["sensor_readings"]
farm_config = db["farm_config"]
weather_cache = db["weather_cache"]
decisions = db["decisions"]
pump_commands = db["pump_commands"]
audit_log = db["audit_log"]
training_labels = db["training_labels"]

readings.create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])
decisions.create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])
devices.create_index([("owner", ASCENDING)])
users.create_index([("role", ASCENDING), ("status", ASCENDING)])
audit_log.create_index([("at", DESCENDING)])

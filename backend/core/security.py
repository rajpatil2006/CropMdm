"""
Accounts, login tokens, roles and device keys.

* Passwords: PBKDF2-HMAC-SHA256 with a random salt (Python standard library).
* Login: a signed JWT (HS256) sent as "Authorization: Bearer <token>".
* Roles: "admin" (everything) and "farmer" (only devices assigned to them).
* ESP32 devices: a random key per device, sent as the "X-Device-Key" header;
  only its SHA-256 hash is stored.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import db

PBKDF2_ITERATIONS = 240_000
TOKEN_HOURS = 12
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def _jwt_secret():
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    # First run: create a strong secret and keep it in .env so logins survive restarts
    secret = secrets.token_urlsafe(48)
    with open(ENV_PATH, "a", encoding="utf-8") as f:
        f.write(f"\nJWT_SECRET={secret}\n")
    os.environ["JWT_SECRET"] = secret
    print("Generated JWT_SECRET and saved it to backend/.env")
    return secret


JWT_SECRET = _jwt_secret()


# ---------------------------------------------------------------- passwords

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def temporary_password():
    return secrets.token_urlsafe(9)


# ---------------------------------------------------------------- tokens

def create_token(user):
    now = datetime.now(timezone.utc)
    payload = {"sub": user["_id"], "role": user["role"], "iat": now, "exp": now + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from exc

    user = db.users.find_one({"_id": payload.get("sub")})
    if user is None or user.get("status") != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not active")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def device_for_user(device_id, user):
    """The device document if this user may access it, else 404/403."""
    device = db.devices.find_one({"_id": device_id})
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if user["role"] != "admin" and device.get("owner") != user["_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This device belongs to another farmer")
    return device


# ---------------------------------------------------------------- device keys

def new_device_key():
    return secrets.token_urlsafe(24)


def hash_device_key(key):
    return hashlib.sha256(key.encode()).hexdigest()

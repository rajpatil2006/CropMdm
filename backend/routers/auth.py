"""Sign-up, login and the logged-in user's own profile."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from core import audit, db
from core.security import create_token, current_user, hash_password, verify_password
from schemas import LoginRequest, PasswordChange, ProfileUpdate, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])

PUBLIC_FIELDS = ("name", "phone", "village", "role", "status", "language", "created_at", "last_login")


def public_user(user):
    out = {"username": user["_id"]}
    for field in PUBLIC_FIELDS:
        value = user.get(field)
        out[field] = value.isoformat() if isinstance(value, datetime) else value
    return out


@router.post("/register", status_code=201)
def register(body: RegisterRequest):
    """Farmer self sign-up. The account can log in once an admin approves it."""
    if db.users.find_one({"_id": body.username}):
        raise HTTPException(status.HTTP_409_CONFLICT, "This username is already taken")
    user = {
        "_id": body.username,
        "name": body.name.strip(),
        "phone": body.phone.strip(),
        "village": body.village.strip(),
        "language": body.language,
        "role": "farmer",
        "status": "pending",
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    }
    db.users.insert_one(user)
    audit.record(user, "register")
    return {"username": user["_id"], "status": "pending"}


@router.post("/login")
def login(body: LoginRequest):
    user = db.users.find_one({"_id": body.username.strip().lower()})
    if user is None or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    if user["status"] == "pending":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is waiting for admin approval")
    if user["status"] in ("rejected", "disabled"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is not active. Contact the admin.")

    now = datetime.now(timezone.utc)
    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": now}})
    audit.record(user, "login")
    user["last_login"] = now
    return {"token": create_token(user), "user": public_user(user)}


@router.get("/me")
def me(user=Depends(current_user)):
    return public_user(user)


@router.patch("/me")
def update_me(body: ProfileUpdate, user=Depends(current_user)):
    changes = body.model_dump(exclude_none=True)
    if changes:
        db.users.update_one({"_id": user["_id"]}, {"$set": changes})
        user.update(changes)
    return public_user(user)


@router.post("/change-password")
def change_password(body: PasswordChange, user=Depends(current_user)):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(body.new_password),
                                                        "must_change_password": False}})
    audit.record(user, "change_password")
    return {"ok": True}

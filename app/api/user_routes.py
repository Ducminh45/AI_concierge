import hashlib
import uuid
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.jwt_auth import SECRET_KEY, ALGORITHM
from ..auth.auth_mixins import get_current_user, get_admin_user
from ..database.db import DatabaseManager

router = APIRouter(prefix="/api/v1", tags=["auth"])

# --- Password Hashing Helper ---
def hash_password(password: str) -> str:
    salt = uuid.uuid4().hex
    pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{pwd_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    if ":" not in stored_hash:
        return False
    salt, pwd_hash = stored_hash.split(":", 1)
    return hashlib.sha256((password + salt).encode()).hexdigest() == pwd_hash


# --- Token Generator ---
def create_access_token(username: str, role: str, expires_delta: timedelta | None = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode = {
        "sub": username,
        "role": role,
        "exp": int(expire.timestamp())
    }
    return pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# --- Pydantic Models ---
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[str] = None
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class RoleUpdate(BaseModel):
    role: str = Field(..., description="Role must be admin, staff, or guest")


# --- Auth Routes ---

@router.post("/auth/register")
async def register_user(request: Request, body: UserRegister):
    raise HTTPException(status_code=404, detail="Registration is disabled in login-less mode")


@router.post("/auth/login")
async def login_user(request: Request, body: UserLogin):
    raise HTTPException(status_code=404, detail="Login is disabled in login-less mode")


@router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "ok": True,
        "user": {
            "username": current_user["username"],
            "email": current_user["email"],
            "full_name": current_user["full_name"],
            "role": current_user["role"]
        }
    }


# --- Admin User Management Routes ---

@router.get("/users")
async def list_users(request: Request, _admin: dict = Depends(get_admin_user)):
    db: DatabaseManager = request.app.state.db
    users = db.get_all_users()
    # Clean sensitive info before returning
    for u in users:
        u.pop("password_hash", None)
    return {
        "ok": True,
        "users": users
    }


@router.put("/users/{username}/role")
async def update_role(request: Request, username: str, body: RoleUpdate, _admin: dict = Depends(get_admin_user)):
    db: DatabaseManager = request.app.state.db
    
    if body.role not in ["admin", "staff", "guest"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin', 'staff', or 'guest'")
        
    user = db.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Prevent self-demotion from admin
    if username.lower() == _admin["username"].lower() and body.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot demote yourself from admin")
        
    db.update_user_role(username, body.role)
    return {
        "ok": True,
        "message": f"Updated role for {username} to {body.role}"
    }

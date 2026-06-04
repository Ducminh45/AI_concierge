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
    db: DatabaseManager = request.app.state.db
    
    # Check if user already exists
    existing = db.get_user(body.username)
    if existing:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại / Username already exists")
        
    pwd_hash = hash_password(body.password)
    
    # Auto-assign 'admin' role to first user, otherwise 'guest'
    all_users = db.get_all_users()
    role = "admin" if len(all_users) == 0 else "guest"
    
    try:
        user_dict = db.create_user(
            username=body.username,
            password_hash=pwd_hash,
            email=body.email,
            full_name=body.full_name,
            role=role
        )
        # Auto-login after registration
        token = create_access_token(body.username, role)
        return {
            "ok": True,
            "message": "Đăng ký tài khoản thành công / Registration successful",
            "token": token,
            "user": user_dict
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {e}")


@router.post("/auth/login")
async def login_user(request: Request, body: UserLogin):
    db: DatabaseManager = request.app.state.db
    
    user = db.get_user(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Tài khoản hoặc mật khẩu không chính xác / Incorrect username or password")
        
    token = create_access_token(user["username"], user["role"])
    
    return {
        "ok": True,
        "token": token,
        "user": {
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }


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

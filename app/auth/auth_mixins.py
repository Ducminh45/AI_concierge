import jwt as pyjwt
from fastapi import Header, HTTPException, Request, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .jwt_auth import SECRET_KEY, ALGORITHM
from ..config import get_settings
from ..database.db import DatabaseManager

security = HTTPBearer(auto_error=False)


def _is_managed_api_key(token: str) -> bool:
    return token.startswith(("mr_", "rc_"))


def _api_key_user(user_id: str) -> dict:
    return {
        "id": 0,
        "username": user_id,
        "email": None,
        "full_name": "Managed API Key User",
        "role": "admin",
    }


async def get_current_user(
    request: Request,
    x_api_key: str = Header(default=None),
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    settings = get_settings()
    db: DatabaseManager = request.app.state.db
    manager = getattr(request.app.state, "api_key_manager", None)

    username = None
    managed_key_user = False

    # 1. Try X-API-Key header
    if x_api_key:
        token = x_api_key.strip()
        if token == settings.api_key.strip():
            # Return a mock static admin user
            return {
                "id": 0,
                "username": "api_key_admin",
                "email": "admin@resort.com",
                "full_name": "API Key Admin",
                "role": "admin",
            }
        if manager and _is_managed_api_key(token):
            user_id = manager.verify_key(token)
            if user_id:
                manager.log_usage(token, endpoint=request.url.path, success=True)
                username = user_id
                managed_key_user = True
            else:
                manager.log_usage(token, endpoint=request.url.path, success=False)

    # 2. Try Authorization Bearer header
    if not username and credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials.strip()

        if token == settings.api_key.strip():
            return {
                "id": 0,
                "username": "api_key_admin",
                "email": "admin@resort.com",
                "full_name": "API Key Admin",
                "role": "admin",
            }

        if manager and _is_managed_api_key(token):
            user_id = manager.verify_key(token)
            if user_id:
                manager.log_usage(token, endpoint=request.url.path, success=True)
                username = user_id
                managed_key_user = True
            else:
                manager.log_usage(token, endpoint=request.url.path, success=False)

        if not username:
            # JWT check
            try:
                payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username = payload.get("sub")
            except Exception:
                pass

    if username:
        # Check database
        user = db.get_user(username)
        if user:
            return user
        if managed_key_user or username == "api_key_user":
            return _api_key_user(username)

    raise HTTPException(status_code=401, detail="Invalid token or not authenticated")


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permissions required")
    return current_user


async def get_staff_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Staff permissions required")
    return current_user


# Alias for backward compatibility
jwt_or_api_key = get_current_user

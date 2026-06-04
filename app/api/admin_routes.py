from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.auth_mixins import jwt_or_api_key
from ..auth.security import APIKeyManager


# --- Pydantic models ---

class CreateKeyRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Owner of the new key")
    expires_days: int = Field(default=90, ge=1, le=365)


class CreateKeyResponse(BaseModel):
    raw_key: str
    user_id: str
    expires_days: int
    message: str = "Store this key securely - it will not be shown again."


class KeyInfo(BaseModel):
    key_id: str
    user_id: str
    created_at: str
    expires_at: Optional[str]
    last_used_at: Optional[str]
    is_active: bool


class UsageEntry(BaseModel):
    id: int
    key_id: str
    user_id: Optional[str]
    endpoint: str
    timestamp: str
    success: bool


# --- Dependency ---

def get_api_key_manager(request: Request) -> APIKeyManager:
    manager = getattr(request.app.state, "api_key_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="API key manager not available")
    return manager


# --- Router ---

router = APIRouter(prefix="/admin/api-keys", tags=["admin"])


@router.post("", response_model=CreateKeyResponse)
async def create_api_key(
    body: CreateKeyRequest,
    _user: str = Depends(jwt_or_api_key),
    manager: APIKeyManager = Depends(get_api_key_manager),
):
    raw_key = manager.create_key(body.user_id, expires_days=body.expires_days)
    return CreateKeyResponse(
        raw_key=raw_key,
        user_id=body.user_id,
        expires_days=body.expires_days,
    )


@router.get("", response_model=list[KeyInfo])
async def list_api_keys(
    user_id: Optional[str] = None,
    _user: str = Depends(jwt_or_api_key),
    manager: APIKeyManager = Depends(get_api_key_manager),
):
    return manager.list_keys(user_id=user_id)


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    _user: str = Depends(jwt_or_api_key),
    manager: APIKeyManager = Depends(get_api_key_manager),
):
    if not manager.revoke_key(key_id):
        raise HTTPException(status_code=404, detail="Key not found")
    return {"ok": True, "detail": f"Key {key_id} revoked"}


@router.get("/usage", response_model=list[UsageEntry])
async def get_usage(
    key_id: Optional[str] = None,
    limit: int = 100,
    _user: str = Depends(jwt_or_api_key),
    manager: APIKeyManager = Depends(get_api_key_manager),
):
    return manager.get_usage(key_hash=key_id, limit=limit)

from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.auth_mixins import get_current_user, get_staff_user
from ..database.db import DatabaseManager

router = APIRouter(prefix="/api/v1", tags=["services"])

# --- Pydantic Models ---
class ServiceRequestCreate(BaseModel):
    room_number: Optional[str] = None
    resort_name: Optional[str] = None
    service_type: str = Field(..., description="Service type, e.g., 'Extra Towels', 'Room Cleaning', etc.")
    details: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str = Field(..., description="Status must be 'pending', 'in_progress', 'completed', or 'cancelled'")


# --- Service Request Routes ---

@router.post("/service-requests")
async def create_service_request(
    request: Request,
    body: ServiceRequestCreate,
    current_user: dict = Depends(get_current_user)
):
    db: DatabaseManager = request.app.state.db
    
    # We can use the username as session_id to group requests per user
    session_id = current_user["username"]
    guest_name = current_user.get("full_name") or current_user["username"]
    
    try:
        new_req = db.create_service_request(
            session_id=session_id,
            room_number=body.room_number,
            guest_name=guest_name,
            resort_name=body.resort_name,
            service_type=body.service_type,
            details=body.details
        )
        return {
            "ok": True,
            "message": "Yêu cầu dịch vụ đã được ghi nhận / Service request submitted",
            "request": new_req
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit request: {e}")


@router.get("/service-requests")
async def list_service_requests(
    request: Request,
    all: bool = False,
    current_user: dict = Depends(get_current_user)
):
    db: DatabaseManager = request.app.state.db
    
    # If requesting all service requests, verify user has staff/admin permissions
    if all:
        if current_user.get("role") not in ["admin", "staff"]:
            raise HTTPException(status_code=403, detail="Staff permissions required to list all requests")
        reqs = db.get_service_requests(all_requests=True)
    else:
        # Standard users only see their own requests (mapped by username)
        reqs = db.get_service_requests(session_id=current_user["username"])
        
    return {
        "ok": True,
        "requests": reqs
    }


@router.put("/service-requests/{request_id}/status")
async def update_request_status(
    request: Request,
    request_id: int,
    body: StatusUpdate,
    _staff: dict = Depends(get_staff_user)
):
    db: DatabaseManager = request.app.state.db
    
    if body.status not in ["pending", "in_progress", "completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'pending', 'in_progress', 'completed', or 'cancelled'")
        
    # Check if request exists
    # Simple lookup using list
    reqs = db.get_service_requests(all_requests=True)
    target = None
    for r in reqs:
        if r["id"] == request_id:
            target = r
            break
            
    if not target:
        raise HTTPException(status_code=404, detail="Service request not found")
        
    db.update_service_request_status(request_id, body.status)
    return {
        "ok": True,
        "message": f"Updated service request #{request_id} status to {body.status}"
    }

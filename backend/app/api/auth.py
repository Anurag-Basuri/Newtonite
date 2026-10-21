"""
Authentication API endpoints: login, logout, me.
Matches docs/API_SPEC.md §3.1.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Response, Request
from pydantic import BaseModel, EmailStr
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.core.config import get_settings
from app.db.client import get_database
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    user: Dict[str, Any]
    teams: List[Dict[str, Any]]


class MeResponse(BaseModel):
    user: Dict[str, Any]
    is_org_admin: bool
    teams: List[Dict[str, Any]]


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncDatabase = Depends(get_database),
):
    """
    Authenticate with email and password.
    Sets HttpOnly, SameSite cookie and returns user profile & memberships.
    """
    cfg = get_settings()
    auth_service = AuthService(db)
    user_summary, token, memberships = await auth_service.login(
        email=payload.email,
        password=payload.password,
        user_agent=request.headers.get("user-agent", ""),
        ip=request.client.host if request.client else "",
    )

    response.set_cookie(
        key=cfg.COOKIE_NAME,
        value=token,
        max_age=cfg.SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=cfg.COOKIE_SECURE,
        samesite=cfg.COOKIE_SAMESITE,
        path="/",
    )
    return {"user": user_summary, "teams": memberships}


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    request: Request,
    db: AsyncDatabase = Depends(get_database),
):
    """Revoke session and clear session cookie."""
    cfg = get_settings()
    token = request.cookies.get(cfg.COOKIE_NAME)
    if token:
        auth_service = AuthService(db)
        await auth_service.logout(token)

    response.delete_cookie(key=cfg.COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
async def me(
    auth_data: tuple = Depends(get_current_user_and_memberships),
):
    """Return authenticated caller identity, org admin status, and team memberships."""
    user, memberships = auth_data
    return {
        "user": user,
        "is_org_admin": user.get("is_org_admin", False),
        "teams": memberships,
    }

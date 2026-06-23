"""
auth.py
=======
JWT authentication helpers and the /api/auth/* router.

Only /api/auth/login is public. Every other /api/* route calls
`require_auth` as a FastAPI dependency, which validates the Bearer token.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/api/auth")
_bearer = HTTPBearer()


# ── Token helpers ──────────────────────────────────────────────────────────────

def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ── Dependency injected into every protected route ─────────────────────────────

def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    payload = _decode_token(credentials.credentials)
    return payload["sub"]


# ── Login endpoint (the only public route) ─────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if body.username != settings.auth_user or body.password != settings.auth_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = _create_token(body.username)
    return LoginResponse(access_token=token)

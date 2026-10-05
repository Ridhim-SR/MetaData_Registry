import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session
from database.models import User

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Unknown/legacy hash format -> treat as mismatch (401), not 500
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["sub"] = str(to_encode.get("sub", ""))
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = int(payload.get("sub", 0))
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Only users with role == admin."""
    if user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Authenticated user when a valid Bearer token is present, else None.

    Used by public registry endpoints so anonymous users see public metadata
    while logged-in users additionally see their department's metadata.
    Invalid tokens are treated as anonymous (not 401) on public routes.
    """
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        return None
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def user_context(user: User | None) -> dict | None:
    """Minimal policy context for visibility helpers (never trust the client)."""
    if user is None:
        return None
    return {"role": user.role.value, "department": user.department}


def scoped_service(user: User, requested_service: str | None) -> str | None:
    """Enforce department scoping: non-admin users are pinned to their department.

    Convention: user.department maps 1:1 to an OM database service name
    (e.g. department 'agriculture' -> service 'gov_agriculture', or the raw
    service name if it already matches). Admins may query any service.
    Returns the effective service filter to apply.
    """
    if user.role.value == "admin":
        return requested_service
    if not user.department:
        # No department assigned: safest is to return the requested filter
        # unchanged; deployment may choose to deny instead.
        return requested_service
    dept = user.department.strip()
    candidates = {dept, f"gov_{dept}", dept.replace("gov_", "")}
    if requested_service is None:
        return None  # filtering happens post-fetch via allowed_services()
    if requested_service in candidates:
        return requested_service
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied for service '{requested_service}'",
    )


def allowed_services(user: User) -> set[str] | None:
    """Set of OM service names a non-admin user may see, or None for admins / unscoped."""
    if user.role.value == "admin" or not user.department:
        return None
    dept = user.department.strip()
    return {dept, f"gov_{dept}", dept.replace("gov_", "")}

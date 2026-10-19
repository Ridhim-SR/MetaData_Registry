import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session
from database.models import AuthProvider, User, UserRole

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

# user_id -> (expires_at, profile fields). Per worker process. Skips one
# Neon US round-trip (~1.5-4 s) per DB-verified request. Invalidated on
# PUT /users/{id} in the worker that handled it; otherwise at most
# _USER_CACHE_TTL stale for role/department/profile. Never holds passwords.
_USER_CACHE: dict[int, tuple[float, dict]] = {}
_USER_CACHE_TTL = 600.0


def invalidate_user_cache(user_id: int) -> None:
    _USER_CACHE.pop(user_id, None)


def _cached_user(user_id: int) -> User | None:
    hit = _USER_CACHE.get(user_id)
    if not hit:
        return None
    expires_at, data = hit
    if time.monotonic() > expires_at:
        _USER_CACHE.pop(user_id, None)
        return None
    try:
        return User(
            id=user_id,
            username=data["username"],
            email=data["email"],
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            role=UserRole(data["role"]),
            department=data.get("department"),
            # Every field /auth/me returns must be cached: a missing
            # auth_provider made MeResponse fail (500) on cache hits.
            auth_provider=AuthProvider(data.get("auth_provider") or AuthProvider.local.value),
        )
    except Exception:
        _USER_CACHE.pop(user_id, None)
        return None


def _store_user_cache(user: User) -> None:
    try:
        _USER_CACHE[user.id] = (
            time.monotonic() + _USER_CACHE_TTL,
            {
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
                "department": user.department,
                "auth_provider": (
                    user.auth_provider.value
                    if isinstance(user.auth_provider, AuthProvider)
                    else user.auth_provider
                ),
            },
        )
    except Exception:
        pass


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Unknown/legacy hash format -> treat as mismatch (401), not 500
        return False


async def hash_password_async(password: str) -> str:
    """Off-loop bcrypt hash (~100-300ms CPU) so the event loop stays free."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    """Off-loop bcrypt verify so concurrent requests don't stall."""
    return await asyncio.to_thread(verify_password, plain, hashed)


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
    cached = _cached_user(user_id)
    if cached is not None:
        return cached
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    _store_user_cache(user)
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
    """Viewer for read-only public registry endpoints, from the token alone.

    Anonymous (no/invalid token) -> None. Otherwise the signed token's own
    claims (sub, role, department -- set at login) decide visibility, with
    no database round-trip. The returned User is transient: only id, role
    and department are set. Trade-off: a role/department change reaches
    these read endpoints when the user next logs in or the token expires
    (ACCESS_TOKEN_EXPIRE_MINUTES). Tokens without these claims fall back
    to the DB-verified lookup. Endpoints that write or need the profile
    use get_optional_user_verified / get_current_user instead.
    """
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    try:
        user_id = int(payload.get("sub", 0))
        role = UserRole(payload["role"])
    except (KeyError, TypeError, ValueError):
        return await get_optional_user_verified(credentials, session)
    if user_id <= 0:
        return None
    return User(id=user_id, role=role, department=payload.get("department"))


async def get_optional_user_verified(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Authenticated user loaded from the database (cached), else None.

    For optional-auth endpoints that write or need profile fields (email);
    invalid tokens are treated as anonymous (not 401).
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
    cached = _cached_user(user_id)
    if cached is not None:
        return cached
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        _store_user_cache(user)
    return user


def user_context(user: User | None) -> dict | None:
    """Minimal policy context for visibility helpers (never trust the client)."""
    if user is None:
        return None
    return {"role": user.role.value, "department": user.department}


def scoped_service(user: User, requested_service: str | None) -> str | None:
    """Resolve the requested service filter without department pinning.

    Authenticated users may discover datasets across departments; the
    visibility sidecar (public/department/restricted/confidential) is the
    enforcement point, not the department filter. The ``department`` /
    ``service`` query parameter remains as an optional Owner filter only.
    Returns the requested filter unchanged.
    """
    return requested_service


def allowed_services(user: User) -> set[str] | None:
    """Pre-filter hint for OM fetches. Always None: cross-department.

    Discovery across departments is allowed for authenticated users; the
    per-table visibility policy (src.openmetadata.visibility) decides full
    vs teaser vs hidden after the fetch. Returning None disables
    service-name pre-filtering so authorization happens post-fetch before
    counts, facets, pagination, or metadata are produced.
    """
    return None

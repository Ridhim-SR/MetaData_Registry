from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuthProvider, User, UserRole
from src.middleware.auth import create_access_token, hash_password, verify_password
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


def _username_from_email(email: str) -> str:
    return email.split("@")[0][:50]


async def _unique_username(base: str, session: AsyncSession) -> str:
    candidate = base or "user"
    suffix = 0
    while True:
        name = candidate if suffix == 0 else f"{candidate[:44]}{suffix}"
        existing = await session.execute(select(User.id).where(User.username == name))
        if existing.scalar_one_or_none() is None:
            return name
        suffix += 1


async def register_user(body: RegisterRequest, session: AsyncSession):
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    username = await _unique_username(_username_from_email(body.email), session)
    # Role is always 'user' on self-registration. Admins promote via PUT /users/{id}.
    user = User(
        username=username,
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        password_hash=hash_password(body.password),
        auth_provider=AuthProvider.local,
        role=UserRole.user,
        department=body.department,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "department": user.department,
        "auth_provider": user.auth_provider,
    }


async def login_user(body: LoginRequest, session: AsyncSession) -> TokenResponse:
    identifier = body.email.strip()
    result = await session.execute(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"This account uses {user.auth_provider.value} sign-in. Please continue with {user.auth_provider.value}.",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": user.id, "role": user.role.value, "department": user.department})
    return TokenResponse(access_token=token)

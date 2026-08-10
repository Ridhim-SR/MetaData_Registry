from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from src.middleware.auth import create_access_token, hash_password, verify_password
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


async def register_user(body: RegisterRequest, session: AsyncSession):
    existing = await session.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    await session.commit()
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role}


async def login_user(body: LoginRequest, session: AsyncSession) -> TokenResponse:
    result = await session.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": user.id, "role": user.role.value})
    return TokenResponse(access_token=token)

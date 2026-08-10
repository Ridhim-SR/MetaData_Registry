from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session
from database.models import User
from src.middleware.auth import get_current_user
from src.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from src.services.auth import login_user, register_user

router = APIRouter(tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    return await register_user(body, session)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    return await login_user(body, session)


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, username=user.username, email=user.email, role=user.role)

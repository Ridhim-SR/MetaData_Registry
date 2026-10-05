import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # apps/api/.env (server-only, gitignored) before local imports read env

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import async_session, engine
from database.database import get_session as db_get_session
from database.models import Base, User, UserRole
from database.schemas import UserOut
from src.middleware.auth import get_current_user, require_admin
from src.openmetadata.config import settings as om_settings
from src.routers import app_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight dev migration for pre-existing databases
        await conn.execute(text("ALTER TABLE users.users ADD COLUMN IF NOT EXISTS department VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE users.users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE users.users ADD COLUMN IF NOT EXISTS last_name VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE users.users ADD COLUMN IF NOT EXISTS provider_sub VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE users.users ALTER COLUMN password_hash DROP NOT NULL"))
        await conn.execute(text("DO $$ BEGIN CREATE TYPE users.auth_provider AS ENUM ('local', 'google', 'microsoft'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"))
        await conn.execute(text("ALTER TABLE users.users ADD COLUMN IF NOT EXISTS auth_provider users.auth_provider NOT NULL DEFAULT 'local'"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_department ON users.users (department)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_provider ON users.users (auth_provider, provider_sub)"))
    yield
    await engine.dispose()


app = FastAPI(title="Backend", lifespan=lifespan)

cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(app_router)


@app.exception_handler(httpx.ConnectError)
async def om_unreachable_handler(request: Request, exc: httpx.ConnectError):
    return JSONResponse(
        status_code=503,
        content={
            "detail": f"Cannot connect to OpenMetadata server at {om_settings.host}. "
            "Is it running?",
        },
    )


@app.exception_handler(httpx.HTTPStatusError)
async def om_status_handler(request: Request, exc: httpx.HTTPStatusError):
    status_code = exc.response.status_code if exc.response is not None else 502
    if status_code == 404:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    if status_code in (401, 403):
        return JSONResponse(status_code=502, content={"detail": "OpenMetadata rejected the credentials"})
    return JSONResponse(status_code=502, content={"detail": f"OpenMetadata error: {status_code}"})


@app.get("/")
async def root(session: AsyncSession = Depends(db_get_session)):
    from sqlalchemy.exc import DBAPIError

    try:
        result = await session.execute(text("SELECT version()"))
    except DBAPIError:
        # Stale pooled handle via the WS bridge — retry once on a fresh checkout.
        await session.rollback()
        result = await session.execute(text("SELECT version()"))
    return {"message": "Hello from backend", "db": result.scalar()}


@app.get("/users", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(db_get_session),
    _admin: User = Depends(require_admin),
):
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()


@app.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: dict,
    session: AsyncSession = Depends(db_get_session),
    _admin: User = Depends(require_admin),
):
    """Admin-only: promote/demote role or (re)assign department."""
    from fastapi import HTTPException

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if "role" in body and body["role"] is not None:
        try:
            user.role = UserRole(body["role"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid role")
    if "department" in body:
        user.department = body["department"]
    await session.commit()
    await session.refresh(user)
    return user

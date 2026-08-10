from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import async_session, engine
from database.models import Base, User
from database.schemas import UserOut
from src.openmetadata.config import settings as om_settings
from src.routers import app_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Backend", lifespan=lifespan)
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


async def get_session():
    async with async_session() as session:
        yield session


@app.get("/")
async def root(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("SELECT version()"))
    return {"message": "Hello from backend", "db": result.scalar()}


@app.get("/users", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()

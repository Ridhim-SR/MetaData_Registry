from fastapi import APIRouter

from src.routers.auth import router as auth_router
from src.openmetadata.routers.ingestion import router as om_ingestion_router
from src.openmetadata.routers.metadata import router as om_metadata_router

app_router = APIRouter()
app_router.include_router(auth_router, prefix="/auth")
app_router.include_router(om_ingestion_router)
app_router.include_router(om_metadata_router)

from fastapi import APIRouter

from src.routers.auth import router as auth_router
from src.routers.oauth import router as oauth_router
from src.openmetadata.routers.ingestion import router as om_ingestion_router
from src.openmetadata.routers.metadata import router as om_metadata_router
from src.openmetadata.routers.datasets import router as om_datasets_router
from src.openmetadata.routers.tags import router as om_tags_router
from src.openmetadata.routers.search import router as om_search_router
from src.openmetadata.routers.registry import router as registry_router

app_router = APIRouter()
app_router.include_router(auth_router, prefix="/auth")
app_router.include_router(oauth_router)
app_router.include_router(registry_router)
app_router.include_router(om_ingestion_router)
app_router.include_router(om_metadata_router)
app_router.include_router(om_datasets_router)
app_router.include_router(om_tags_router)
app_router.include_router(om_search_router)

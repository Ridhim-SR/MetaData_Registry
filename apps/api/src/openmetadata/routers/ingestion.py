import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from database.models import User
from src.middleware.auth import get_current_user
from src.openmetadata.client import OpenMetadataClient
from src.openmetadata.ingestion.connectors import PostgresConnector, CsvConnector
from src.openmetadata.schemas.ingestion import (
    PipelineTriggerRequest,
    PipelineTriggerResponse,
    PostgresIngestionConfig,
    CsvIngestionConfig,
    IngestionPipelineDef,
    CsvUploadResponse,
)

router = APIRouter(prefix="/openmetadata/ingestion", tags=["openmetadata"])

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _save_upload(src, dest: Path) -> int:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    with dest.open("wb") as out:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError("too_large")
            out.write(chunk)
    return dest.stat().st_size


@router.post("/csv/upload", response_model=CsvUploadResponse)
async def upload_csv(file: UploadFile, _user: User = Depends(get_current_user)) -> CsvUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are allowed")

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"

    try:
        size = await asyncio.to_thread(_save_upload, file.file, dest)
    except ValueError:
        raise HTTPException(status_code=413, detail="CSV larger than 50MB is not allowed")
    finally:
        try:
            await asyncio.to_thread(file.file.close)
        except Exception:
            pass

    return CsvUploadResponse(
        file_path=str(dest),
        filename=safe_name,
        size=size,
    )


@router.post("/postgres")
async def ingest_postgres(config: PostgresIngestionConfig, _user: User = Depends(get_current_user)) -> PipelineTriggerResponse:
    async with OpenMetadataClient() as client:
        connector = PostgresConnector(config.model_dump())
        result = await connector.ingest(client)
    return PipelineTriggerResponse(
        status="ok",
        pipeline_id="postgres_ingestion",
        detail=result,
    )


@router.post("/csv")
async def ingest_csv(config: CsvIngestionConfig, _user: User = Depends(get_current_user)) -> PipelineTriggerResponse:
    async with OpenMetadataClient() as client:
        connector = CsvConnector(config.model_dump())
        result = await connector.ingest(client)
    return PipelineTriggerResponse(
        status="ok",
        pipeline_id="csv_ingestion",
        detail=result,
    )


@router.post("/pipelines/trigger")
async def trigger_pipeline(req: PipelineTriggerRequest, _user: User = Depends(get_current_user)) -> PipelineTriggerResponse:
    async with OpenMetadataClient() as client:
        result = await client.trigger_ingestion_pipeline(req.pipeline_id)
    return PipelineTriggerResponse(
        status="triggered",
        pipeline_id=req.pipeline_id,
        detail=result,
    )


@router.get("/pipelines")
async def list_pipelines(_user: User = Depends(get_current_user)) -> list[dict]:
    async with OpenMetadataClient() as client:
        return await client.list_ingestion_pipelines()


@router.post("/pipelines")
async def create_pipeline(pipeline: IngestionPipelineDef, _user: User = Depends(get_current_user)) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_ingestion_pipeline(pipeline.model_dump(exclude_none=True))


@router.get("/health")
async def check_health() -> dict:
    async with OpenMetadataClient() as client:
        return await client.health()

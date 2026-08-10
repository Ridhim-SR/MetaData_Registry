import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

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


@router.post("/csv/upload", response_model=CsvUploadResponse)
async def upload_csv(file: UploadFile) -> CsvUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are allowed")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"

    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return CsvUploadResponse(
        file_path=str(dest),
        filename=safe_name,
        size=dest.stat().st_size,
    )


@router.post("/postgres")
async def ingest_postgres(config: PostgresIngestionConfig) -> PipelineTriggerResponse:
    async with OpenMetadataClient() as client:
        connector = PostgresConnector(config.model_dump())
        result = await connector.ingest(client)
    return PipelineTriggerResponse(
        status="ok",
        pipeline_id="postgres_ingestion",
        detail=result,
    )


@router.post("/csv")
async def ingest_csv(config: CsvIngestionConfig) -> PipelineTriggerResponse:
    async with OpenMetadataClient() as client:
        connector = CsvConnector(config.model_dump())
        result = await connector.ingest(client)
    return PipelineTriggerResponse(
        status="ok",
        pipeline_id="csv_ingestion",
        detail=result,
    )


@router.post("/pipelines/trigger")
async def trigger_pipeline(req: PipelineTriggerRequest) -> PipelineTriggerResponse:
    async with OpenMetadataClient() as client:
        result = await client.trigger_ingestion_pipeline(req.pipeline_id)
    return PipelineTriggerResponse(
        status="triggered",
        pipeline_id=req.pipeline_id,
        detail=result,
    )


@router.get("/pipelines")
async def list_pipelines() -> list[dict]:
    async with OpenMetadataClient() as client:
        return await client.list_ingestion_pipelines()


@router.post("/pipelines")
async def create_pipeline(pipeline: IngestionPipelineDef) -> dict:
    async with OpenMetadataClient() as client:
        return await client.create_ingestion_pipeline(pipeline.model_dump(exclude_none=True))


@router.get("/health")
async def check_health() -> dict:
    async with OpenMetadataClient() as client:
        return await client.health()

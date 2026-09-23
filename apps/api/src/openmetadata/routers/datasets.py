from anyio import to_thread
from fastapi import APIRouter, HTTPException

from src.openmetadata.schemas.dataset import DatasetCreate, DatasetResponse
from src.openmetadata.service import store_dataset

router = APIRouter(prefix="/openmetadata/metadata", tags=["openmetadata"])


@router.post("/tables", response_model=DatasetResponse, status_code=201)
async def create_table_metadata(payload: DatasetCreate) -> DatasetResponse:
    try:
        table = await to_thread.run_sync(store_dataset, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - map SDK errors to a clean response
        message = str(exc) or "OpenMetadata rejected the metadata"
        if "401" in message or "Unauthorized" in message:
            raise HTTPException(
                status_code=502,
                detail="OpenMetadata rejected the credentials. Check OPENMETADATA_JWT_TOKEN.",
            )
        raise HTTPException(status_code=502, detail=message[:500])
    return DatasetResponse(
        success=True,
        message="Metadata stored successfully",
        data={
            "name": table["name"],
            "fully_qualified_name": table["fully_qualified_name"],
            "id": table["id"],
        },
    )

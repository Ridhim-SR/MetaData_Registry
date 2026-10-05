from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session as db_get_session
from database.models import User
from src.middleware.auth import get_current_user
from src.openmetadata.schemas.dataset import DatasetCreate, DatasetResponse
from src.openmetadata.service import store_dataset

router = APIRouter(prefix="/openmetadata/metadata", tags=["openmetadata"])


@router.post("/tables", response_model=DatasetResponse, status_code=201)
async def create_table_metadata(
    payload: DatasetCreate,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_get_session),
) -> DatasetResponse:
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
    # Record access metadata (FastAPI is the policy enforcement point).
    from src.openmetadata.routers.registry import upsert_table_info, upsert_table_visibility

    await upsert_table_visibility(
        session,
        fqn=table["fully_qualified_name"],
        visibility=payload.visibility,
        department=payload.department,
    )
    await upsert_table_info(
        session,
        fqn=table["fully_qualified_name"],
        api_available=payload.api_available,
        dataset_owner=payload.dataset_owner,
        frequency=payload.frequency,
        timeline=payload.timeline,
    )
    return DatasetResponse(
        success=True,
        message="Metadata stored successfully",
        data={
            "name": table["name"],
            "fully_qualified_name": table["fully_qualified_name"],
            "id": table["id"],
        },
    )

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_session
from src.schemas.auth import OAuthCallbackRequest, OAuthURLResponse, TokenResponse
from src.services.oauth import authorization_url, handle_callback

router = APIRouter(prefix="/auth/oauth", tags=["auth-oauth"])


@router.get("/{provider}/login-url", response_model=OAuthURLResponse)
async def oauth_login_url(
    provider: str,
    redirect_uri: str = Query(description="Frontend callback URL registered with the provider"),
    state: str | None = Query(default=None, description="Opaque value round-tripped for CSRF protection"),
):
    return OAuthURLResponse(authorization_url=authorization_url(provider, redirect_uri, state))


@router.post("/{provider}/callback", response_model=TokenResponse)
async def oauth_callback(
    provider: str,
    body: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_session),
):
    return await handle_callback(provider, body.code, body.redirect_uri, session)

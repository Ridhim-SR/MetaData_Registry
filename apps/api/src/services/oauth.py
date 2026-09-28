"""Social sign-in (Google / Microsoft) via OAuth2 authorization-code flow.

The browser is redirected to the provider, which sends back a one-time `code`.
This service exchanges the code server-side (client secret never leaves the
backend), fetches the verified profile, then finds-or-creates the local user
and returns our own JWT — so the rest of the platform works unchanged.

Required env (per provider, else its endpoints answer 501):
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
  MICROSOFT_CLIENT_ID / MICROSOFT_CLIENT_SECRET (+ optional MICROSOFT_TENANT, default "common")
"""

import os
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuthProvider, User, UserRole
from src.middleware.auth import create_access_token
from src.schemas.auth import TokenResponse
from src.services.auth import _unique_username, _username_from_email

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_GOOGLE_SCOPES = "openid email profile"

_MICROSOFT_SCOPES = "openid profile email User.Read"


def _microsoft_tenant() -> str:
    return os.getenv("MICROSOFT_TENANT", "common")


def _microsoft_auth_url() -> str:
    return f"https://login.microsoftonline.com/{_microsoft_tenant()}/oauth2/v2.0/authorize"


def _microsoft_token_url() -> str:
    return f"https://login.microsoftonline.com/{_microsoft_tenant()}/oauth2/v2.0/token"


def _google_conf() -> tuple[str, str] | None:
    cid, secret = os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")
    return (cid, secret) if cid and secret else None


def _microsoft_conf() -> tuple[str, str] | None:
    cid, secret = os.getenv("MICROSOFT_CLIENT_ID"), os.getenv("MICROSOFT_CLIENT_SECRET")
    return (cid, secret) if cid and secret else None


def _check_provider(provider: str) -> AuthProvider:
    try:
        return AuthProvider(provider)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'")
    if provider == "local":
        raise HTTPException(status_code=400, detail="Local accounts use email + password")


def authorization_url(provider: str, redirect_uri: str, state: str | None = None) -> str:
    ap = _check_provider(provider)
    if ap == AuthProvider.google:
        conf = _google_conf()
        if not conf:
            raise HTTPException(status_code=501, detail="Google sign-in is not configured (GOOGLE_CLIENT_ID/SECRET)")
        params = {
            "client_id": conf[0],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _GOOGLE_SCOPES,
            "access_type": "online",
            "prompt": "select_account",
        }
        if state:
            params["state"] = state
        return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
    conf = _microsoft_conf()
    if not conf:
        raise HTTPException(status_code=501, detail="Microsoft sign-in is not configured (MICROSOFT_CLIENT_ID/SECRET)")
    params = {
        "client_id": conf[0],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _MICROSOFT_SCOPES,
    }
    if state:
        params["state"] = state
    return f"{_microsoft_auth_url()}?{urlencode(params)}"


async def _google_profile(code: str, redirect_uri: str) -> dict:
    conf = _google_conf()
    if not conf:
        raise HTTPException(status_code=501, detail="Google sign-in is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": conf[0],
                "client_secret": conf[1],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Google rejected the login. Please try again.")
        access_token = token_resp.json().get("access_token")
        info_resp = await client.get(
            _GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        info_resp.raise_for_status()
        info = info_resp.json()
    if not info.get("email"):
        raise HTTPException(status_code=401, detail="Google did not return an email address")
    return {
        "sub": info["sub"],
        "email": info["email"],
        "first_name": info.get("given_name"),
        "last_name": info.get("family_name"),
    }


async def _microsoft_profile(code: str, redirect_uri: str) -> dict:
    conf = _microsoft_conf()
    if not conf:
        raise HTTPException(status_code=501, detail="Microsoft sign-in is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            _microsoft_token_url(),
            data={
                "code": code,
                "client_id": conf[0],
                "client_secret": conf[1],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": _MICROSOFT_SCOPES,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Microsoft rejected the login. Please try again.")
        access_token = token_resp.json().get("access_token")
        me_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        me_resp.raise_for_status()
        me = me_resp.json()
    email = me.get("mail") or me.get("userPrincipalName")
    if not email:
        raise HTTPException(status_code=401, detail="Microsoft did not return an email address")
    return {
        "sub": me["id"],
        "email": email,
        "first_name": me.get("givenName"),
        "last_name": me.get("surname"),
    }


async def handle_callback(
    provider: str, code: str, redirect_uri: str, session: AsyncSession
) -> TokenResponse:
    ap = _check_provider(provider)
    if ap == AuthProvider.google:
        profile = await _google_profile(code, redirect_uri)
    else:
        profile = await _microsoft_profile(code, redirect_uri)

    # 1. Known social account -> log in
    result = await session.execute(
        select(User).where(User.auth_provider == ap, User.provider_sub == profile["sub"])
    )
    user = result.scalar_one_or_none()

    # 2. Same email registered another way -> link the provider to it
    if user is None:
        result = await session.execute(select(User).where(User.email == profile["email"]))
        user = result.scalar_one_or_none()
        if user is not None:
            user.auth_provider = ap
            user.provider_sub = profile["sub"]
            user.first_name = user.first_name or profile.get("first_name")
            user.last_name = user.last_name or profile.get("last_name")
            await session.commit()

    # 3. Brand new email -> auto-create a dept-less user (admin assigns dept later)
    if user is None:
        user = User(
            username=await _unique_username(_username_from_email(profile["email"]), session),
            email=profile["email"],
            first_name=profile.get("first_name"),
            last_name=profile.get("last_name"),
            password_hash=None,
            auth_provider=ap,
            provider_sub=profile["sub"],
            role=UserRole.user,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token({"sub": user.id, "role": user.role.value, "department": user.department})
    return TokenResponse(access_token=token)

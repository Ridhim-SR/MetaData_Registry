"""The sidecar cache never makes a request wait on a reload once loaded."""

import asyncio
import contextlib
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.openmetadata.routers import registry  # noqa: E402


def test_stale_cache_is_served_while_one_background_reload_runs(monkeypatch):
    @contextlib.asynccontextmanager
    async def fake_session():
        yield "background-session"

    monkeypatch.setattr(registry, "_background_session", fake_session)
    release = asyncio.Event()
    calls: list[str] = []

    async def loader(session):
        calls.append(session)
        if len(calls) > 1:
            await release.wait()  # a slow database
        return {"version": len(calls)}

    async def scenario():
        cache = registry._SidecarCache(loader)
        assert await cache.get("request-session") == {"version": 1}  # first load waits
        cache._hit = (time.monotonic() - registry.SIDECAR_TTL_SECONDS - 1, cache._hit[1])
        # Expired: both requests get the old copy at once; one reload starts.
        assert await cache.get("request-session") == {"version": 1}
        assert await cache.get("request-session") == {"version": 1}
        await asyncio.sleep(0)
        assert calls == ["request-session", "background-session"]
        release.set()
        await cache._refresh
        assert await cache.get("request-session") == {"version": 2}

    asyncio.run(scenario())


def test_failed_reload_keeps_the_cached_copy(monkeypatch):
    @contextlib.asynccontextmanager
    async def fake_session():
        yield None

    monkeypatch.setattr(registry, "_background_session", fake_session)
    calls = 0

    async def loader(session):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("database down")
        return {"ok": True}

    async def scenario():
        cache = registry._SidecarCache(loader)
        await cache.get(None)
        cache._hit = (time.monotonic() - registry.SIDECAR_TTL_SECONDS - 1, cache._hit[1])
        assert await cache.get(None) == {"ok": True}
        await cache._refresh
        # Still served, and not retried on every request until a TTL passes.
        assert await cache.get(None) == {"ok": True}
        assert cache._refresh is None and calls == 2

    asyncio.run(scenario())

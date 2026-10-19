"""Per-request timing breakdown: where does a request's time go?

Each request gets a RequestTimings object in a context variable (set by the
middleware in main.py). Instrumented code adds to it:

- db:     wall time inside AsyncSession calls (execute/commit/...), which
          includes pool checkout, pre-ping and any new connection;
- dbconn: of which, opening new database connections (count + time);
- om:     time inside OpenMetadata HTTP calls (count + time).

The middleware reports the result as a `Server-Timing` response header
(shown in the browser DevTools "Timing" tab) and one log line per request.
Code running outside a request (startup, background tasks) records nothing.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestTimings:
    db_ms: float = 0.0
    db_calls: int = 0
    connect_ms: float = 0.0
    connects: int = 0
    om_ms: float = 0.0
    om_calls: int = 0
    # perf_counter() when a new DB connection started opening (see database.py).
    connect_started: float | None = None


_current: ContextVar[RequestTimings | None] = ContextVar("request_timings", default=None)


def begin() -> RequestTimings:
    """Start collecting for the current request (called by the middleware)."""
    timings = RequestTimings()
    _current.set(timings)
    return timings


def current() -> RequestTimings | None:
    return _current.get()


@contextmanager
def track(kind: str):
    """Add the wall time of the enclosed block to `kind` ("db" or "om")."""
    timings = _current.get()
    if timings is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        if kind == "db":
            timings.db_ms += elapsed
            timings.db_calls += 1
        else:
            timings.om_ms += elapsed
            timings.om_calls += 1


def connect_started() -> None:
    timings = _current.get()
    if timings is not None:
        timings.connect_started = time.perf_counter()


def connect_finished() -> None:
    timings = _current.get()
    if timings is not None and timings.connect_started is not None:
        timings.connect_ms += (time.perf_counter() - timings.connect_started) * 1000
        timings.connects += 1
        timings.connect_started = None


def server_timing_header(timings: RequestTimings, total_ms: float) -> str:
    other = max(total_ms - timings.db_ms - timings.om_ms, 0.0)
    return ", ".join([
        f'db;dur={timings.db_ms:.1f};desc="DB ({timings.db_calls} calls)"',
        f'dbconn;dur={timings.connect_ms:.1f};desc="New DB connections ({timings.connects})"',
        f'om;dur={timings.om_ms:.1f};desc="OpenMetadata ({timings.om_calls} calls)"',
        f'app;dur={other:.1f};desc="App (CPU, serialization)"',
        f'total;dur={total_ms:.1f}',
    ])


def log_line(method: str, path: str, status: int, timings: RequestTimings, total_ms: float) -> str:
    other = max(total_ms - timings.db_ms - timings.om_ms, 0.0)
    return (
        f"timing {method} {path} {status} total={total_ms:.0f}ms "
        f"db={timings.db_ms:.0f}ms/{timings.db_calls} "
        f"(new_conn={timings.connect_ms:.0f}ms/{timings.connects}) "
        f"om={timings.om_ms:.0f}ms/{timings.om_calls} app={other:.0f}ms"
    )

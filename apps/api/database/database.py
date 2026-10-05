import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/appdb",
)


def _split_sslmode(url: str) -> tuple[str, dict]:
    """Translate libpq-style query params into asyncpg connect args.

    asyncpg understands neither ``sslmode`` nor ``channel_binding`` (both
    appear in Neon connection strings), so strip them from the URL and pass
    the equivalent ``ssl`` flag instead. URLs without these parameters keep
    existing local (non-SSL) behaviour unchanged.
    """
    scheme, netloc, path, query, fragment = urlsplit(url)
    params = dict(parse_qsl(query, keep_blank_values=True))
    mode = (params.pop("sslmode", "") or "").lower()
    params.pop("channel_binding", None)  # libpq-only; asyncpg rejects it
    connect_args: dict = {}
    if "-pooler" in netloc:
        # Neon PgBouncer (transaction mode) cannot use prepared statements.
        connect_args["statement_cache_size"] = 0
    if mode in {"require", "prefer", "verify-ca", "verify-full"}:
        connect_args["ssl"] = True
    elif mode == "disable":
        connect_args["ssl"] = False
    clean = urlunsplit((scheme, netloc, path, urlencode(params), fragment))
    return clean, connect_args


_DATABASE_URL, _CONNECT_ARGS = _split_sslmode(DATABASE_URL)

engine = create_async_engine(
    _DATABASE_URL,
    connect_args=_CONNECT_ARGS,
    pool_size=5,
    max_overflow=10,
    # The Neon WebSocket bridge (127.0.0.1:5433 on blocked hosts) drops
    # idle connections; without pre-ping the pool reuses dead handles and
    # every pooled query intermittently fails with "connection is closed".
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with async_session() as session:
        yield session

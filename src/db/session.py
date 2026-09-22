from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(
    database_url: str,
    *,
    pool_size: int = 10,
    pool_recycle: int = 1800,
    tls_ca_path: Path | None = None,
) -> AsyncEngine:
    connect_args: dict = {}
    if tls_ca_path is not None:
        ssl_context = ssl.create_default_context(cafile=str(tls_ca_path))
        # The platform database contract is VERIFY_CA. asyncpg (through libpq)
        # would otherwise upgrade VERIFY_CA to a full identity check and reject
        # the server certificate may be auto-generated without a SAN. We therefore
        # keep certificate verification ON but skip
        # the hostname check, preserving the VERIFY_CA semantics.
        ssl_context.check_hostname = False
        # asyncpg accepts the SSL configuration via its `ssl` connect argument
        # (an ssl.SSLContext or the string "require"/"verify-ca"/"verify-full"),
        # which is passed through SQLAlchemy's connect_args.
        connect_args["ssl"] = ssl_context
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=pool_recycle,
        pool_size=pool_size,
        **({"connect_args": connect_args} if connect_args else {}),
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session

"""Lazy database/Redis resources owned by the FastAPI application."""

from collections.abc import AsyncIterator
from typing import cast

from fastapi import FastAPI, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from jaldrishti_api.config import Settings


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_engine(request: Request) -> AsyncEngine:
    """Create the connection pool on first use, not during module import."""

    engine = getattr(request.app.state, "database_engine", None)
    if engine is None:
        engine = create_async_engine(
            _settings(request).database_url,
            pool_pre_ping=True,
        )
        request.app.state.database_engine = engine
        request.app.state.session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return cast(AsyncEngine, engine)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    get_engine(request)
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        yield session


async def get_redis(request: Request) -> Redis:
    client = getattr(request.app.state, "redis_client", None)
    if client is None:
        client = Redis.from_url(_settings(request).redis_url, decode_responses=True)
        request.app.state.redis_client = client
    return cast(Redis, client)


async def close_resources(app: FastAPI) -> None:
    """Close only resources that were actually used by this process."""

    state = app.state
    engine = getattr(state, "database_engine", None)
    if engine is not None:
        await engine.dispose()
    redis = getattr(state, "redis_client", None)
    if redis is not None:
        await redis.aclose()

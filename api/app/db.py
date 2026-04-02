"""Shared database and normalization helpers for Cue2Case API routers."""

import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Dict, Optional

import psycopg2
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL_ASYNC")
    if not database_url:
        raise HTTPException(status_code=500, detail="Database URL is not configured")
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


@contextmanager
def get_db_cursor():
    connection = psycopg2.connect(get_database_url(), cursor_factory=RealDictCursor)
    try:
        with connection.cursor() as cursor:
            yield cursor
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    return value


def normalize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: normalize_value(value) for key, value in row.items()}

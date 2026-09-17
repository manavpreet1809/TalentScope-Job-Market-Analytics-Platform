"""Application configuration from the process environment.

Required: DB_HOST, DB_NAME, DB_USER, DB_PASSWORD.
Optional: DB_PORT (defaults to 5432).
JSearch requires RAPIDAPI_KEY; RAPIDAPI_HOST defaults to jsearch.p.rapidapi.com.
No environment files are loaded and no connection is opened on import.
"""

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL


def get_jsearch_headers() -> dict:
    """Read RapidAPI settings only when the JSearch client needs them."""
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not key:
        raise ValueError("Missing required API setting: RAPIDAPI_KEY")
    if "\r" in key or "\n" in key:
        raise ValueError("RAPIDAPI_KEY must be a single-line value")
    host = os.environ.get("RAPIDAPI_HOST", "jsearch.p.rapidapi.com").strip()
    if host != "jsearch.p.rapidapi.com":
        raise ValueError("RAPIDAPI_HOST must be jsearch.p.rapidapi.com")
    return {"X-RapidAPI-Key": key, "X-RapidAPI-Host": host}


def get_database_url() -> URL:
    """Validate settings and build a URL without interpolating credentials."""
    required = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
    values = {name: os.environ.get(name, "") for name in required}
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise ValueError("Missing required database settings: " + ", ".join(missing))

    try:
        port = int(os.environ.get("DB_PORT", "5432"))
    except ValueError:
        raise ValueError("DB_PORT must be an integer between 1 and 65535") from None
    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT must be an integer between 1 and 65535")

    return URL.create(
        "postgresql+psycopg2",
        username=values["DB_USER"],
        password=values["DB_PASSWORD"],
        host=values["DB_HOST"],
        port=port,
        database=values["DB_NAME"],
    )


@lru_cache(maxsize=1)
def get_db_engine() -> Engine:
    """Reuse a lazy engine; restart the process after changing DB settings.

    Connections are opened only when a caller uses the engine. Stale pooled
    connections are checked before use, and SQL parameter logging is hidden.
    """
    return create_engine(
        get_database_url(), pool_pre_ping=True, hide_parameters=True
    )

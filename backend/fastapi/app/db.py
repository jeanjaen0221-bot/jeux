import os
from contextlib import contextmanager
from typing import Iterator
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+" not in url[:20]:
        # Prefer psycopg v3 driver if not explicitly specified
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

_DATABASE_URL = os.getenv("DATABASE_URL")
if not _DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required (Postgres), e.g. postgresql+psycopg://USER:PASS@HOST:PORT/DBNAME")
_DATABASE_URL = _normalize_url(_DATABASE_URL)

engine: Engine = create_engine(_DATABASE_URL, future=True)

@contextmanager
def session() -> Iterator:
    with engine.begin() as conn:
        yield conn

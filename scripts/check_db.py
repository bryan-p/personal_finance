#!/usr/bin/env python3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))
from app.core.config import get_settings  # noqa: E402


try:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
except Exception as exc:
    print(f"PostgreSQL connection failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
print("PostgreSQL connection verified.")

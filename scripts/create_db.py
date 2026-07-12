#!/usr/bin/env python3
import sys

import psycopg
from psycopg import sql

sys.path.insert(0, "backend")
from app.core.config import get_settings  # noqa: E402


settings = get_settings()
connection = psycopg.connect(
    host=settings.database_host,
    port=settings.database_port,
    dbname="postgres",
    user=settings.database_user,
    password=settings.database_password,
    sslmode=settings.database_ssl_mode,
    autocommit=True,
)
with connection:
    exists = connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (settings.database_name,)
    ).fetchone()
    if exists:
        print(f'Database "{settings.database_name}" already exists.')
    else:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.database_name)))
        print(f'Created database "{settings.database_name}".')


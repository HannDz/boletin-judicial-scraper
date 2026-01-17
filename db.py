from __future__ import annotations
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from configuration import settings


def build_database_url() -> str:
    backend = settings.db_backend.lower()

    if backend in ("postgres", "postgresql"):
        # Postgres (psycopg)
        user = quote_plus(settings.db_user)
        pwd = quote_plus(settings.db_password)
        host = settings.db_host
        port = settings.db_port
        db = settings.db_name
        return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}"

    if backend in ("mssql", "sqlserver", "sql_server"):
        # SQL Server (pyodbc) - por si mañana lo activas
        # Requiere: pip install pyodbc
        driver = quote_plus(getattr(settings, "db_driver", "ODBC Driver 18 for SQL Server"))
        trust = getattr(settings, "db_trust_cert", "yes")
        trust_cert = "yes" if str(trust).lower() in ("1", "true", "yes", "y") else "no"

        user = quote_plus(settings.db_user)
        pwd = quote_plus(settings.db_password)
        host = settings.db_host
        port = settings.db_port
        db = settings.db_name

        return (
            f"mssql+pyodbc://{user}:{pwd}@{host}:{port}/{db}"
            f"?driver={driver}&Encrypt=yes&TrustServerCertificate={trust_cert}"
        )

    raise ValueError(f"DB_BACKEND no soportado: {backend}")


DATABASE_URL = build_database_url()

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

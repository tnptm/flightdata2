import polars as pl
from sqlalchemy import MetaData, Table, create_engine
from sqlmodel import SQLModel

from src.config import DB_URL
from src.models import FlightSnapshot, IncidentTrack  # noqa: F401 — registers tables


def create_db_and_tables(db_url: str | None = None) -> None:
    url = db_url or DB_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)


def log_to_postgres(df: pl.DataFrame, table: str, db_url: str | None = None) -> None:
    url = db_url or DB_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(url)
    with engine.begin() as conn:
        tbl = Table(table, MetaData(), autoload_with=engine)
        conn.execute(tbl.insert(), df.to_dicts())

from datetime import datetime

import polars as pl
from sqlalchemy import MetaData, Table, create_engine
from sqlmodel import Session, SQLModel

from src.config import DB_URL
from src.models import FlightBatch, FlightSnapshot, IncidentTrack  # noqa: F401 — registers tables


def create_db_and_tables(db_url: str | None = None) -> None:
    url = db_url or DB_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)


def create_batch(saved_at: datetime, flight_count: int, db_url: str | None = None) -> int:
    url = db_url or DB_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(url)
    with Session(engine) as session:
        batch = FlightBatch(saved_at=saved_at, flight_count=flight_count)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return batch.id


def update_batch_warning(batch_id: int | None, warning: str, db_url: str | None = None) -> None:
    """Append a warning string to the batch record. No-op when batch_id is None."""
    if batch_id is None:
        return
    url = db_url or DB_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(url)
    with Session(engine) as session:
        batch = session.get(FlightBatch, batch_id)
        if batch:
            batch.detection_warning = (
                f"{batch.detection_warning}\n{warning}" if batch.detection_warning else warning
            )
            session.add(batch)
            session.commit()


def log_to_postgres(df: pl.DataFrame, table: str, db_url: str | None = None) -> None:
    url = db_url or DB_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_engine(url)
    with engine.begin() as conn:
        tbl = Table(table, MetaData(), autoload_with=engine)
        conn.execute(tbl.insert(), df.to_dicts())

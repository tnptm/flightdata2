"""Tests for database setup and the log_to_postgres helper."""
from datetime import datetime, timezone

import polars as pl
from sqlmodel import Session, create_engine, select

from src.database import create_batch, log_to_postgres, update_batch_warning
from src.models import FlightBatch, FlightSnapshot, IncidentTrack
from tests.conftest import make_batch


def test_create_db_and_tables_creates_all_tables(db_url):
    engine = create_engine(db_url)
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "flight_batches" in tables
    assert "flight_snapshots" in tables
    assert "incident_tracks" in tables


def test_create_batch_returns_id(db_url):
    batch_id = create_batch(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc), 42, db_url=db_url)
    assert isinstance(batch_id, int)
    assert batch_id >= 1


def test_create_batch_stored_correctly(db_url):
    saved_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    batch_id = create_batch(saved_at, 100, db_url=db_url)
    engine = create_engine(db_url)
    with Session(engine) as session:
        batch = session.get(FlightBatch, batch_id)
    assert batch.flight_count == 100
    assert batch.detection_warning is None


def test_update_batch_warning_sets_warning(db_url):
    batch_id = make_batch(db_url)
    update_batch_warning(batch_id, "INCIDENT: AB1234 last_alt=5000m", db_url=db_url)
    engine = create_engine(db_url)
    with Session(engine) as session:
        batch = session.get(FlightBatch, batch_id)
    assert batch.detection_warning == "INCIDENT: AB1234 last_alt=5000m"


def test_update_batch_warning_appends_multiple(db_url):
    batch_id = make_batch(db_url)
    update_batch_warning(batch_id, "INCIDENT: AA0001 last_alt=3000m", db_url=db_url)
    update_batch_warning(batch_id, "INCIDENT: BB0002 last_alt=8000m", db_url=db_url)
    engine = create_engine(db_url)
    with Session(engine) as session:
        batch = session.get(FlightBatch, batch_id)
    assert "AA0001" in batch.detection_warning
    assert "BB0002" in batch.detection_warning


def test_update_batch_warning_noop_when_batch_id_none(db_url):
    # Should not raise
    update_batch_warning(None, "INCIDENT: XX1234", db_url=db_url)


def test_log_flight_snapshot(db_url):
    batch_id = make_batch(db_url)
    df = pl.DataFrame([{
        "batch_id": batch_id,
        "icao24": "AB1234",
        "callsign": "TST001",
        "time": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "latitude": 50.0,
        "longitude": 10.0,
        "baro_altitude": 5000.0,
        "velocity": 250.0,
        "heading": 90.0,
        "on_ground": False,
    }])
    log_to_postgres(df, "flight_snapshots", db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        rows = session.exec(select(FlightSnapshot)).all()
    assert len(rows) == 1
    assert rows[0].icao24 == "AB1234"
    assert rows[0].baro_altitude == 5000.0
    assert rows[0].batch_id == batch_id


def test_log_multiple_snapshots(db_url):
    batch_id = make_batch(db_url, flight_count=5)
    rows_data = [
        {"batch_id": batch_id, "icao24": f"XX{i:04d}", "callsign": f"F{i:04d}",
         "time": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
         "latitude": float(i), "longitude": float(i),
         "baro_altitude": float(i * 100), "velocity": 250.0,
         "heading": 90.0, "on_ground": False}
        for i in range(5)
    ]
    log_to_postgres(pl.DataFrame(rows_data), "flight_snapshots", db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        count = len(session.exec(select(FlightSnapshot)).all())
    assert count == 5


def test_log_incident_track(db_url):
    df = pl.DataFrame([{
        "icao24": "AB1234",
        "callsign": "TST001",
        "path_data": '[{"lat":50.0,"lon":10.0}]',
        "event_timestamp": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }])
    log_to_postgres(df, "incident_tracks", db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        rows = session.exec(select(IncidentTrack)).all()
    assert len(rows) == 1
    assert rows[0].icao24 == "AB1234"

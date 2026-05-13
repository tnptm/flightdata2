"""Tests for database setup and the log_to_postgres helper."""
from datetime import datetime, timezone

import polars as pl
from sqlmodel import Session, create_engine, select

from src.database import log_to_postgres
from src.models import FlightSnapshot, IncidentTrack


def test_create_db_and_tables_creates_both_tables(db_url):
    engine = create_engine(db_url)
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "flight_snapshots" in tables
    assert "incident_tracks" in tables


def test_log_flight_snapshot(db_url):
    df = pl.DataFrame([{
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


def test_log_multiple_snapshots(db_url):
    rows_data = [
        {"icao24": f"XX{i:04d}", "callsign": f"F{i:04d}",
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

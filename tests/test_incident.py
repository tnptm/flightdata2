"""Tests for fetch_and_store_track (incident.py)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

#import pytest
from sqlmodel import Session, create_engine, select

from src.incident import fetch_and_store_track
from src.models import IncidentTrack

LAST_TIME = int(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())


def _make_waypoint(lat, lon, alt):
    wp = MagicMock()
    wp.__dict__ = {"latitude": lat, "longitude": lon, "baro_altitude": alt,
                   "true_track": 90.0, "velocity": 250.0, "on_ground": False}
    return wp


def _mock_api_with_track(icao: str = "AB1234", callsign: str = "TST001"):
    api = MagicMock()
    track = MagicMock()
    track.callsign = callsign
    track.path = [
        _make_waypoint(50.0, 10.0, 5000.0),
        _make_waypoint(50.1, 10.1, 4800.0),
    ]
    api.get_track_by_aircraft.return_value = track
    return api


def test_track_stored_in_database(db_url):
    api = _mock_api_with_track("AB1234", "TST001")
    fetch_and_store_track(api, "AB1234", LAST_TIME, db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        rows = session.exec(select(IncidentTrack)).all()

    assert len(rows) == 1
    assert rows[0].icao24 == "AB1234"
    assert rows[0].callsign == "TST001"
    assert rows[0].path_data is not None


def test_track_stores_correct_event_timestamp(db_url):
    api = _mock_api_with_track()
    fetch_and_store_track(api, "AB1234", LAST_TIME, db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        row = session.exec(select(IncidentTrack)).first()

    expected = datetime.fromtimestamp(LAST_TIME, tz=timezone.utc)
    # SQLite loses tzinfo on round-trip; compare naive UTC
    stored = row.event_timestamp.replace(tzinfo=timezone.utc) if row.event_timestamp.tzinfo is None else row.event_timestamp
    assert stored == expected


def test_no_row_when_track_has_no_path(db_url):
    api = MagicMock()
    track = MagicMock()
    track.path = []
    api.get_track_by_aircraft.return_value = track

    fetch_and_store_track(api, "AB1234", LAST_TIME, db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        rows = session.exec(select(IncidentTrack)).all()
    assert len(rows) == 0


def test_no_row_when_api_returns_none(db_url):
    api = MagicMock()
    api.get_track_by_aircraft.return_value = None

    fetch_and_store_track(api, "AB1234", LAST_TIME, db_url=db_url)

    engine = create_engine(db_url)
    with Session(engine) as session:
        rows = session.exec(select(IncidentTrack)).all()
    assert len(rows) == 0


def test_api_exception_does_not_propagate(db_url):
    api = MagicMock()
    api.get_track_by_aircraft.side_effect = RuntimeError("network error")
    # Should not raise
    fetch_and_store_track(api, "AB1234", LAST_TIME, db_url=db_url)

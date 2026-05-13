from datetime import datetime, timezone

import pytest
from src.database import create_batch, create_db_and_tables
from src.models import FlightBatch, FlightSnapshot, IncidentTrack  # noqa: F401 — registers tables with SQLModel metadata


@pytest.fixture()
def db_url(tmp_path):
    """File-based SQLite database, recreated fresh for every test."""
    url = f"sqlite:///{tmp_path}/test.db"
    create_db_and_tables(url)
    yield url


def make_batch(db_url: str, flight_count: int = 1) -> int:
    """Insert a FlightBatch row and return its id."""
    return create_batch(
        saved_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        flight_count=flight_count,
        db_url=db_url,
    )


def make_state(
    icao: str = "AB1234",
    alt: float | None = 5000.0,
    on_ground: bool = False,
    t: datetime | None = None,
    squawk: str | None = None,
    spi: bool = False,
) -> dict:
    """Build a minimal state dict matching the shape produced by _build_state()."""
    return {
        "icao24": icao,
        "callsign": "TST001",
        "time": t or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "latitude": 50.0,
        "longitude": 10.0,
        "baro_altitude": alt,
        "velocity": 250.0,
        "heading": 90.0,
        "on_ground": on_ground,
        "squawk": squawk,
        "spi": spi,
    }

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, text
from sqlmodel import Field, SQLModel


class FlightBatch(SQLModel, table=True):
    __tablename__ = "flight_batches"

    id: Optional[int] = Field(default=None, primary_key=True)
    saved_at: datetime
    flight_count: int
    detection_warning: Optional[str] = Field(default=None)


class FlightSnapshot(SQLModel, table=True):
    __tablename__ = "flight_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="flight_batches.id", index=True)
    icao24: str = Field(max_length=10)
    callsign: Optional[str] = Field(default=None, max_length=10)
    time: datetime = Field(
        sa_column_kwargs={"server_default": text("now()")},
    )
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    baro_altitude: Optional[float] = None
    velocity: Optional[float] = None
    heading: Optional[float] = None
    on_ground: bool = False


class IncidentTrack(SQLModel, table=True):
    __tablename__ = "incident_tracks"

    id: Optional[int] = Field(default=None, primary_key=True)
    icao24: str = Field(max_length=10)
    callsign: Optional[str] = Field(default=None, max_length=10)
    path_data: Optional[str] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    event_timestamp: datetime

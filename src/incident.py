import logging
from datetime import datetime, timezone

import polars as pl
from opensky_api import OpenSkyApi

from src.database import log_to_postgres

log = logging.getLogger(__name__)


def fetch_and_store_track(
    api: OpenSkyApi, icao: str, last_time: int, db_url: str | None = None
) -> None:
    try:
        track = api.get_track_by_aircraft(icao, t=last_time)
        if track and track.path:
            df_track = pl.DataFrame([p.__dict__ for p in track.path])
            incident_df = pl.DataFrame({
                "icao24": [icao],
                "callsign": [track.callsign],
                "path_data": [df_track.write_json()],
                "event_timestamp": [datetime.fromtimestamp(last_time, tz=timezone.utc)],
            })
            log_to_postgres(incident_df, "incident_tracks", db_url=db_url)
            log.info("Incident track stored: icao=%s waypoints=%d", icao, len(track.path))
        else:
            log.warning("No track data returned for %s", icao)
    except Exception as e:
        log.error("Track fetch error for %s: %s", icao, e, exc_info=True)

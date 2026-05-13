import logging
import time
from datetime import datetime, timezone

import polars as pl
from opensky_api import OpenSkyApi, TokenManager

from src.config import (
    GHOST_TIMEOUT,
    INCIDENT_MIN_ALTITUDE,
    OPENSKY_CREDENTIALS,
    POLL_INTERVAL,
)
from src.database import create_batch, create_db_and_tables, log_to_postgres, update_batch_warning
from src.incident import fetch_and_store_track
from src.logging_setup import setup_logging

log = logging.getLogger(__name__)

# Reactive state tracking
_last_known_states: dict = {}  # {icao24: state_dict} — planes seen last poll
_ghosts: dict = {}             # {icao24: {"disappeared_at": int, "last_state": dict}}


def _build_state(s) -> dict:
    return {
        "icao24": s.icao24,
        "callsign": (s.callsign or "").strip(),
        "time": datetime.fromtimestamp(
            s.time_position or s.last_contact, tz=timezone.utc
        ),
        "latitude": s.latitude,
        "longitude": s.longitude,
        "baro_altitude": s.baro_altitude,
        "velocity": s.velocity,
        "heading": s.true_track,
        "on_ground": s.on_ground,
    }


def _process_ghosts(
    api: OpenSkyApi,
    current_icaos: set,
    now: int,
    last_known_states: dict,
    ghosts: dict,
    db_url: str | None = None,
    batch_id: int | None = None,
) -> None:
    # Step 1: move newly vanished planes into the ghost buffer
    for icao in list(last_known_states.keys()):
        if icao not in current_icaos:
            if icao not in ghosts:
                ghosts[icao] = {
                    "disappeared_at": now,
                    "last_state": last_known_states[icao],
                }
            del last_known_states[icao]

    # Step 2: evaluate existing ghosts
    for icao in list(ghosts.keys()):
        if icao in current_icaos:
            # Reappeared — transient coverage gap, discard
            del ghosts[icao]
        elif now - ghosts[icao]["disappeared_at"] >= GHOST_TIMEOUT:
            ghost = ghosts.pop(icao)
            last_state = ghost["last_state"]
            alt = last_state.get("baro_altitude")
            on_ground = last_state.get("on_ground") or False
            if alt is not None and alt > INCIDENT_MIN_ALTITUDE and not on_ground:
                log.warning(
                    "INCIDENT detected: icao=%s missing=%ds last_alt=%.0fm — fetching track",
                    icao, GHOST_TIMEOUT, alt,
                )
                update_batch_warning(
                    batch_id,
                    f"INCIDENT: {icao} last_alt={alt:.0f}m",
                    db_url=db_url,
                )
                fetch_and_store_track(api, icao, int(last_state["time"].timestamp()), db_url=db_url)
            else:
                log.info("Ghost dismissed: icao=%s alt=%s on_ground=%s", icao, alt, on_ground)


def main_loop() -> None:
    setup_logging()
    api = OpenSkyApi(token_manager=TokenManager.from_json_file(OPENSKY_CREDENTIALS))
    create_db_and_tables()
    log.info("Flight tracker started. Polling every %ds.", POLL_INTERVAL)

    while True:
        try:
            response = api.get_states()
            if not response or not response.states:
                log.warning("No response from OpenSky API, skipping cycle.")
                time.sleep(POLL_INTERVAL)
                continue

            now = int(time.time())
            current_icaos: set = set()
            states_list = []

            for s in response.states:
                state = _build_state(s)
                current_icaos.add(state["icao24"])
                states_list.append(state)
                _last_known_states[state["icao24"]] = state

            batch_id = create_batch(
                saved_at=datetime.fromtimestamp(now, tz=timezone.utc),
                flight_count=len(states_list),
            )
            db_rows = [{**s, "batch_id": batch_id} for s in states_list]
            log_to_postgres(pl.DataFrame(db_rows), "flight_snapshots")
            log.info("Stored %d flight states in batch %d (ts=%d)", len(states_list), batch_id, now)

            _process_ghosts(api, current_icaos, now, _last_known_states, _ghosts, batch_id=batch_id)

        except Exception as e:
            log.error("Main loop error: %s", e, exc_info=True)

        time.sleep(POLL_INTERVAL)

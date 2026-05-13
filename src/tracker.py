import logging
import time
from datetime import datetime, timezone

import polars as pl
from opensky_api import OpenSkyApi, TokenManager

from src.config import (
    EMERGENCY_SQUAWKS,
    GHOST_MIN_POLLS,
    GHOST_TIMEOUT,
    INCIDENT_MAX_ALTITUDE,
    INCIDENT_MIN_ALTITUDE,
    OPENSKY_CREDENTIALS,
    POLL_INTERVAL,
    SPI_TIMEOUT,
)
from src.database import create_batch, create_db_and_tables, log_to_postgres, update_batch_warning
from src.incident import fetch_and_store_track
from src.logging_setup import setup_logging

log = logging.getLogger(__name__)

# Reactive state tracking
_last_known_states: dict = {}  # {icao24: state_dict} — planes seen last poll
_ghosts: dict = {}             # {icao24: {"disappeared_at": int, "last_state": dict}}
_seen_counts: dict = {}        # {icao24: int} — total poll cycles each aircraft has been observed


def _build_state(s) -> dict:
    t = s.time_position or s.last_contact
    return {
        "icao24": s.icao24,
        "callsign": (s.callsign or "").strip(),
        "time": datetime.fromtimestamp(t, tz=timezone.utc) if t else datetime.now(tz=timezone.utc),
        "latitude": s.latitude,
        "longitude": s.longitude,
        "baro_altitude": s.baro_altitude,
        "velocity": s.velocity,
        "heading": s.true_track,
        "on_ground": s.on_ground,
        "squawk": s.squawk,
        "spi": bool(s.spi),
    }


def _process_ghosts(
    api: OpenSkyApi,
    current_icaos: set,
    now: int,
    last_known_states: dict,
    ghosts: dict,
    db_url: str | None = None,
    batch_id: int | None = None,
    seen_counts: dict | None = None,
) -> None:
    # Step 1: move newly vanished planes into the ghost buffer
    for icao in list(last_known_states.keys()):
        if icao not in current_icaos:
            if icao not in ghosts:
                last_state = last_known_states[icao]
                squawk = last_state.get("squawk")
                hard_emergency = squawk in EMERGENCY_SQUAWKS  # 7700/7500: bypass everything
                spi_only = last_state.get("spi", False) and not hard_emergency
                # Hard squawks bypass min-polls; SPI still requires it (ATC ident is routine)
                if hard_emergency or seen_counts is None or seen_counts.get(icao, 0) >= GHOST_MIN_POLLS:
                    ghosts[icao] = {
                        "disappeared_at": now,
                        "last_state": last_state,
                        "hard_emergency": hard_emergency,
                        "spi_only": spi_only,
                    }
            del last_known_states[icao]

    # Step 2: evaluate existing ghosts
    for icao in list(ghosts.keys()):
        if icao in current_icaos:
            # Reappeared — transient coverage gap, discard
            del ghosts[icao]
            continue
        ghost = ghosts[icao]
        hard_emergency = ghost.get("hard_emergency", False)
        spi_only = ghost.get("spi_only", False)
        if hard_emergency:
            effective_timeout = 0           # squawk 7700/7500: fire immediately
        elif spi_only:
            effective_timeout = SPI_TIMEOUT  # SPI: shorter wait (~15 min)
        else:
            effective_timeout = GHOST_TIMEOUT  # normal: 30 min
        if now - ghost["disappeared_at"] >= effective_timeout:
            ghosts.pop(icao)
            last_state = ghost["last_state"]
            alt = last_state.get("baro_altitude")
            on_ground = last_state.get("on_ground") or False
            if alt is not None and alt > INCIDENT_MIN_ALTITUDE and alt <= INCIDENT_MAX_ALTITUDE and not on_ground:
                missing_s = now - ghost["disappeared_at"]
                last_signal = last_state["time"].strftime("%Y-%m-%dT%H:%M:%SZ")
                if hard_emergency:
                    squawk = last_state.get("squawk")
                    log.warning(
                        "INCIDENT detected: icao=%s squawk=%s last_alt=%.0fm last_signal=%s — emergency squawk, triggering immediately",
                        icao, squawk, alt, last_signal,
                    )
                elif spi_only:
                    log.warning(
                        "INCIDENT detected: icao=%s spi=True missing=%ds last_alt=%.0fm last_signal=%s — fetching track",
                        icao, missing_s, alt, last_signal,
                    )
                else:
                    log.warning(
                        "INCIDENT detected: icao=%s missing=%ds last_alt=%.0fm last_signal=%s — fetching track",
                        icao, missing_s, alt, last_signal,
                    )
                update_batch_warning(
                    batch_id,
                    f"INCIDENT: {icao} last_alt={alt:.0f}m",
                    db_url=db_url,
                )
                fetch_and_store_track(api, icao, int(last_state["time"].timestamp()), db_url=db_url)
            else:
                if alt is not None and alt > INCIDENT_MAX_ALTITUDE:
                    log.info("Ghost dismissed: icao=%s alt=%.0fm — exceeds max altitude (sensor glitch?)", icao, alt)
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
                icao = state["icao24"]
                current_icaos.add(icao)
                states_list.append(state)
                _last_known_states[icao] = state
                _seen_counts[icao] = _seen_counts.get(icao, 0) + 1

            batch_id = create_batch(
                saved_at=datetime.fromtimestamp(now, tz=timezone.utc),
                flight_count=len(states_list),
            )
            db_rows = [{**s, "batch_id": batch_id} for s in states_list]
            log_to_postgres(pl.DataFrame(db_rows), "flight_snapshots")
            log.info("Stored %d flight states in batch %d (ts=%d)", len(states_list), batch_id, now)

            _process_ghosts(api, current_icaos, now, _last_known_states, _ghosts, batch_id=batch_id, seen_counts=_seen_counts)

        except Exception as e:
            log.error("Main loop error: %s", e, exc_info=True)

        time.sleep(POLL_INTERVAL)

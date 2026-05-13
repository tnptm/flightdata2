"""
Credits tracker for OpenSky API usage.

OpenSky uses three *independent* credit buckets — spending from one does not
affect the others:

  Bucket      Endpoints                                Cost (live / <24 h data)
  ─────────── ──────────────────────────────────────── ────────────────────────
  /states/    get_states() — /states/all, /states/own  4 credits  (/states/own = 0)
  /tracks/    get_track_by_aircraft() — /tracks/all    4 credits
  /flights/   flights/all, arrival, departure …        4 credits

Historical data costs significantly more (30+ credits), but this service only
ever requests live / same-day data, so every call costs a flat 4 credits.

Each bucket has its own daily allowance (`OPENSKY_CREDITS`, default 4 000 for a
Standard User). When a bucket is exhausted, `wait_if_needed` blocks the caller
until midnight UTC resets that bucket.
"""

import logging
import time

from src.config import OPENSKY_CREDITS

log = logging.getLogger(__name__)

# Cost of every live-data (<24 h) request, regardless of endpoint.
_LIVE_COST: int = 4


class _Bucket:
    """One independent credit bucket (states, tracks, or flights)."""

    WINDOW_SECONDS: int = 86400  # 24-hour window

    def __init__(self, name: str, total: int) -> None:
        self.name = name
        self.total = total
        self.used: int = 0
        self.window_start: float = time.time()

    def _maybe_reset(self) -> None:
        if time.time() - self.window_start >= self.WINDOW_SECONDS:
            self.used = 0
            self.window_start = time.time()
            log.info("OpenSky %s bucket reset. Budget restored to %d.", self.name, self.total)

    def _seconds_until_reset(self) -> float:
        return max(0.0, self.WINDOW_SECONDS - (time.time() - self.window_start))

    def charge(self, cost: int) -> None:
        """Charge `cost` credits, blocking if the bucket is exhausted."""
        self._maybe_reset()
        if self.used + cost > self.total:
            wait = self._seconds_until_reset()
            log.warning(
                "OpenSky %s bucket exhausted (%d/%d used). Waiting %.0fs for window reset.",
                self.name, self.used, self.total, wait,
            )
            time.sleep(wait)
            self._maybe_reset()
        self.used += cost
        log.info(
            "OpenSky %s bucket: -%d credits. Used %d/%d in current window.",
            self.name, cost, self.used, self.total,
        )


class CreditsTracker:
    """Tracks credit consumption across all three OpenSky API buckets."""

    def __init__(self) -> None:
        self.states = _Bucket("states", OPENSKY_CREDITS)
        self.tracks = _Bucket("tracks", OPENSKY_CREDITS)
        self.flights = _Bucket("flights", OPENSKY_CREDITS)

    # ------------------------------------------------------------------
    # Public charge methods — one per API call type used in this project
    # ------------------------------------------------------------------

    def charge_states(self) -> None:
        """Charge for one get_states() call (4 credits from the states bucket)."""
        self.states.charge(_LIVE_COST)

    def charge_track(self) -> None:
        """Charge for one get_track_by_aircraft() call (4 credits from the tracks bucket)."""
        self.tracks.charge(_LIVE_COST)


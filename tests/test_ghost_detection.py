"""Tests for the ghost / incident detection state machine (_process_ghosts)."""
#import pytest

from src.config import GHOST_MIN_POLLS, GHOST_TIMEOUT, INCIDENT_MAX_ALTITUDE, INCIDENT_MIN_ALTITUDE, SPI_TIMEOUT
from src.tracker import _process_ghosts
from tests.conftest import make_state

NOW = 1_000_000  # arbitrary fixed timestamp


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _timed_ghost(icao: str, seconds_ago: int, **state_kwargs) -> dict:
    """Pre-populate a ghosts dict entry as if the plane disappeared seconds_ago ago."""
    return {
        "disappeared_at": NOW - seconds_ago,
        "last_state": make_state(icao, **state_kwargs),
    }


# ---------------------------------------------------------------------------
# Step 1: vanishing planes move into the ghost buffer
# ---------------------------------------------------------------------------

def test_vanished_plane_enters_ghost_buffer():
    last = {"AB1234": make_state("AB1234")}
    ghosts: dict = {}
    _process_ghosts(None, set(), NOW, last, ghosts)
    assert "AB1234" in ghosts
    assert "AB1234" not in last


def test_vanished_plane_records_disappeared_at():
    last = {"AB1234": make_state("AB1234")}
    ghosts: dict = {}
    _process_ghosts(None, set(), NOW, last, ghosts)
    assert ghosts["AB1234"]["disappeared_at"] == NOW


def test_present_plane_stays_in_last_known():
    last = {"AB1234": make_state("AB1234")}
    ghosts: dict = {}
    _process_ghosts(None, {"AB1234"}, NOW, last, ghosts)
    assert "AB1234" in last
    assert "AB1234" not in ghosts


def test_ghost_not_duplicated_on_second_absence():
    """A plane already in ghosts should not have its disappeared_at reset."""
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=120)}
    original_time = ghosts["AB1234"]["disappeared_at"]
    _process_ghosts(None, set(), NOW, last, ghosts)
    assert ghosts["AB1234"]["disappeared_at"] == original_time


# ---------------------------------------------------------------------------
# Step 2: ghost evaluation
# ---------------------------------------------------------------------------

def test_reappeared_ghost_is_cleared():
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=120)}
    _process_ghosts(None, {"AB1234"}, NOW, last, ghosts)
    assert "AB1234" not in ghosts


def test_ghost_below_timeout_not_triggered(mocker):
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT - 1, alt=5000.0)}
    _process_ghosts(None, set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()
    assert "AB1234" in ghosts  # still waiting


def test_incident_triggered_at_timeout_with_altitude(mocker):
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT, alt=5000.0, on_ground=False)}
    _process_ghosts(object(), set(), NOW, last, ghosts, db_url=None)
    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args.args[1] == "AB1234"  # icao
    assert "AB1234" not in ghosts  # consumed


def test_incident_not_triggered_when_on_ground(mocker):
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT, alt=5000.0, on_ground=True)}
    _process_ghosts(None, set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()
    assert "AB1234" not in ghosts  # consumed but dismissed


def test_incident_not_triggered_when_alt_too_low(mocker):
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT, alt=INCIDENT_MIN_ALTITUDE - 1)}
    _process_ghosts(None, set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()


def test_incident_not_triggered_when_alt_is_none(mocker):
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT, alt=None)}
    _process_ghosts(None, set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()


def test_incident_triggered_exactly_at_zero_altitude_boundary(mocker):
    """alt=0.0 must NOT trigger — on ground / sea level."""
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT, alt=0.0)}
    _process_ghosts(None, set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# GHOST_MIN_POLLS: planes not yet seen enough times skip ghost buffer
# ---------------------------------------------------------------------------

def test_plane_below_min_polls_skips_ghost_buffer():
    """A plane seen only once (count=1) must not enter the ghost buffer."""
    last = {"AB1234": make_state("AB1234")}
    ghosts: dict = {}
    seen_counts = {"AB1234": 1}
    _process_ghosts(None, set(), NOW, last, ghosts, seen_counts=seen_counts)
    assert "AB1234" not in ghosts
    assert "AB1234" not in last  # still removed from last_known


def test_plane_at_min_polls_enters_ghost_buffer():
    """A plane seen exactly GHOST_MIN_POLLS times must enter the ghost buffer."""
    last = {"AB1234": make_state("AB1234")}
    ghosts: dict = {}
    seen_counts = {"AB1234": GHOST_MIN_POLLS}
    _process_ghosts(None, set(), NOW, last, ghosts, seen_counts=seen_counts)
    assert "AB1234" in ghosts


def test_no_seen_counts_falls_back_to_original_behaviour():
    """When seen_counts is None every vanished plane still enters the ghost buffer."""
    last = {"AB1234": make_state("AB1234")}
    ghosts: dict = {}
    _process_ghosts(None, set(), NOW, last, ghosts, seen_counts=None)
    assert "AB1234" in ghosts


# ---------------------------------------------------------------------------
# Emergency squawk / SPI bypass
# ---------------------------------------------------------------------------

def test_emergency_squawk_bypasses_min_polls(mocker):
    """Squawk 7700 must trigger incident despite seen_count below GHOST_MIN_POLLS."""
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last = {"AB1234": make_state("AB1234", squawk="7700", alt=5000.0)}
    ghosts: dict = {}
    seen_counts = {"AB1234": 1}  # below GHOST_MIN_POLLS
    _process_ghosts(object(), set(), NOW, last, ghosts, seen_counts=seen_counts)
    mock_fetch.assert_called_once()  # triggered despite low seen_count
    assert "AB1234" not in ghosts   # consumed


def test_emergency_squawk_triggers_immediately(mocker):
    """A plane with squawk 7700 triggers on the same cycle it disappears."""
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last = {"AB1234": make_state("AB1234", squawk="7700", alt=5000.0)}
    ghosts: dict = {}
    _process_ghosts(object(), set(), NOW, last, ghosts)
    mock_fetch.assert_called_once()
    assert "AB1234" not in ghosts


def test_spi_flag_respects_min_polls():
    """SPI=True still requires GHOST_MIN_POLLS — ATC ident is too routine for immediate trigger."""
    last = {"AB1234": make_state("AB1234", spi=True, alt=5000.0)}
    ghosts: dict = {}
    seen_counts = {"AB1234": 1}  # below GHOST_MIN_POLLS
    _process_ghosts(None, set(), NOW, last, ghosts, seen_counts=seen_counts)
    assert "AB1234" not in ghosts  # did NOT enter ghost buffer


def test_spi_flag_enters_buffer_when_min_polls_met(mocker):
    """SPI=True enters ghost buffer when seen enough times, but uses SPI_TIMEOUT not 0."""
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    # Pre-populate ghost with spi_only=True, disappeared SPI_TIMEOUT seconds ago
    ghosts = {"AB1234": {
        "disappeared_at": NOW - SPI_TIMEOUT,
        "last_state": make_state("AB1234", spi=True, alt=5000.0),
        "hard_emergency": False,
        "spi_only": True,
    }}
    _process_ghosts(object(), set(), NOW, last, ghosts)
    mock_fetch.assert_called_once()
    assert "AB1234" not in ghosts


def test_spi_ghost_not_triggered_before_spi_timeout(mocker):
    """SPI ghost must not trigger before SPI_TIMEOUT has elapsed."""
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": {
        "disappeared_at": NOW - (SPI_TIMEOUT - 1),
        "last_state": make_state("AB1234", spi=True, alt=5000.0),
        "hard_emergency": False,
        "spi_only": True,
    }}
    _process_ghosts(object(), set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()
    assert "AB1234" in ghosts  # still waiting


def test_non_emergency_squawk_respects_min_polls():
    """A normal squawk code must still respect the min-polls filter."""
    last = {"AB1234": make_state("AB1234", squawk="1234")}
    ghosts: dict = {}
    seen_counts = {"AB1234": 1}
    _process_ghosts(None, set(), NOW, last, ghosts, seen_counts=seen_counts)
    assert "AB1234" not in ghosts


def test_incident_not_triggered_when_alt_exceeds_max(mocker):
    """Altitude above INCIDENT_MAX_ALTITUDE is treated as sensor glitch, not an incident."""
    mock_fetch = mocker.patch("src.tracker.fetch_and_store_track")
    last: dict = {}
    ghosts = {"AB1234": _timed_ghost("AB1234", seconds_ago=GHOST_TIMEOUT, alt=INCIDENT_MAX_ALTITUDE + 1)}
    _process_ghosts(None, set(), NOW, last, ghosts)
    mock_fetch.assert_not_called()
    assert "AB1234" not in ghosts  # consumed but dismissed

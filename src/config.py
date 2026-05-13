import os

# None when not configured — fails at first actual DB call, not at import time
DB_URL: str | None = os.environ.get("DATABASE_URL")
POLL_INTERVAL: int = int(os.environ.get("POLL_INTERVAL", 300))
OPENSKY_CREDENTIALS: str = os.environ.get("OPENSKY_CREDENTIALS", "credentials.json")
# 1800s (30 min): ADS-B gaps under 20 min are routine (oceanic, mountainous terrain, relay gaps)
GHOST_TIMEOUT: int = int(os.environ.get("GHOST_TIMEOUT", 1800))
# 3 polls (~15 min of confirmed tracking) before entering ghost buffer
GHOST_MIN_POLLS: int = int(os.environ.get("GHOST_MIN_POLLS", 3))
INCIDENT_MIN_ALTITUDE: float = 500.0  # metres
# Squawk codes that bypass GHOST_MIN_POLLS and GHOST_TIMEOUT (trigger immediately)
EMERGENCY_SQUAWKS: frozenset[str] = frozenset({"7500", "7700"})  # hijack, general emergency

LOG_FILE: str = os.environ.get("LOG_FILE", "logs/tracker.log")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

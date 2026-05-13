import os

# None when not configured — fails at first actual DB call, not at import time
DB_URL: str | None = os.environ.get("DATABASE_URL")
POLL_INTERVAL: int = int(os.environ.get("POLL_INTERVAL", 300))
OPENSKY_CREDENTIALS: str = os.environ.get("OPENSKY_CREDENTIALS", "credentials.json")
GHOST_TIMEOUT: int = int(os.environ.get("GHOST_TIMEOUT", 600))  # seconds missing before triggering
GHOST_MIN_POLLS: int = int(os.environ.get("GHOST_MIN_POLLS", 2))  # min consecutive polls seen before ghost-tracking
INCIDENT_MIN_ALTITUDE: float = 500.0  # metres

LOG_FILE: str = os.environ.get("LOG_FILE", "logs/tracker.log")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

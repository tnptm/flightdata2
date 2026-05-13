# Flight Tracker Data Collector and Incident Detector Pipeline

Polls the [OpenSky Network](https://opensky-network.org/) API every 5 minutes, stores worldwide aircraft states in PostgreSQL, and reactively detects potential mid-air incidents by monitoring for aircraft that disappear under specific conditions.

## Incident detection logic

Each poll cycle the tracker maintains a **ghost buffer** — aircraft seen previously but absent from the latest API response. A ghost is evaluated against the rules below once per cycle.

### Tier 1 — Normal detection (timeout-based)

| Rule | Value | Reason |
|---|---|---|
| Minimum confirmed polls before ghost-tracking | **3 polls (~15 min)** | Ignores aircraft seen only once; eliminates startup false positives |
| Missing duration before triggering | **30 minutes** (`GHOST_TIMEOUT=1800`) | ADS-B gaps under 20 min are routine (oceanic dead zones, mountainous terrain, relay coverage gaps) |
| Minimum last altitude | **500 m** (`INCIDENT_MIN_ALTITUDE`) | Dismisses landings and low-altitude flight |
| Maximum last altitude | **25 000 m / ~82 000 ft** (`INCIDENT_MAX_ALTITUDE`) | Rejects physically impossible readings as sensor glitches |
| `on_ground = True` | dismissed | Plane was on the ground when last seen |

All five conditions must be satisfied to store a track and write a warning to the batch record.

### Tier 2 — SPI detection (accelerated)

If the last known state has the **SPI flag** (Special Purpose Indicator) set, the aircraft uses a shorter timeout of **~15 minutes** (`SPI_TIMEOUT`, default `GHOST_MIN_POLLS × POLL_INTERVAL`). The minimum-polls filter still applies — the plane must have been confirmed in ≥ 3 polls before the SPI path activates.

Rationale: ATC routinely asks pilots to "squawk ident", which activates SPI for ~18 seconds. A plane that idents and then enters a coverage gap is common. Requiring ≥ 3 confirmed polls before tracking prevents routine idents from flooding the incident log, while the shorter timeout still responds faster than the 30-minute normal path if SPI was a genuine distress signal.

### Tier 3 — Emergency squawk detection (immediate)

If the last known state has **squawk `7700`** (general emergency) or **`7500`** (hijack), the aircraft bypasses both the min-polls filter and all timeouts and triggers on the same cycle it vanishes. These codes require the pilot to manually dial a 4-digit code — accidental activation is extremely rare.

The altitude and on-ground rules apply to all three tiers.

### Dismissal log examples

```
Ghost dismissed: icao=a47477 alt=335.28 on_ground=False        # below 500 m
Ghost dismissed: icao=451cc1 alt=None on_ground=True           # on ground
Ghost dismissed: icao=a420d7 alt=37125m — exceeds max altitude (sensor glitch?)
```

### Incident log examples

```
# Tier 1 — normal timeout
INCIDENT detected: icao=a1a435 missing=1800s last_alt=9243m last_signal=2026-05-13T15:08:42Z — fetching track
# Tier 2 — SPI accelerated
INCIDENT detected: icao=ae1fd4 spi=True missing=900s last_alt=1212m last_signal=2026-05-13T20:22:48Z — fetching track
# Tier 3 — emergency squawk, immediate
INCIDENT detected: icao=71c701 squawk=7700 last_alt=10660m last_signal=2026-05-13T15:08:41Z — emergency squawk, triggering immediately
```

### Configuration

All thresholds can be overridden via environment variables (see [Environment variables](#environment-variables)).

---

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) v2
- An OpenSky Network account with OAuth2 client credentials

---

## Quick start

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd flightdata2
```

### 2. Create the credentials file

Create `credentials.json` in the project root:

```json
{
    "clientId": "your_client_id",
    "clientSecret": "your_client_secret"
}
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set a strong database password:

```dotenv
POSTGRES_USER=flightdata
POSTGRES_PASSWORD=your_strong_password_here
POSTGRES_DB=flightdata

# Keep the host as "db" — it matches the compose service name
DATABASE_URL=postgresql://flightdata:your_strong_password_here@db:5432/flightdata
```

The remaining defaults are fine for most setups. See [Environment variables](#environment-variables) below for the full reference.

### 4. Build and start

```bash
docker compose up --build -d
```

The `app` container waits for PostgreSQL to be healthy before starting. Database tables are created automatically on first run.

### 5. Verify it is running

```bash
# Tail live logs
docker compose logs -f app

# Check both containers are up
docker compose ps
```

---

## Stopping and restarting

```bash
# Stop without removing data
docker compose stop

# Stop and remove containers (data volume is preserved)
docker compose down

# Stop and delete everything including the database volume
docker compose down -v
```

---

## Rebuilding after code changes

```bash
docker compose up --build -d
```

---

## Viewing logs

Application logs are written to `logs/tracker.log` on the host (bind-mounted from the container) and also streamed to stdout.

```bash
# Live stream
docker compose logs -f app

# Read the rotating log file directly
tail -f logs/tracker.log

# Errors only
grep ERROR logs/tracker.log
```

Log files rotate at 10 MB, keeping 5 backups (`tracker.log.1` … `tracker.log.5`).

---

## Connecting to the database

The host port is set by `POSTGRES_PORT_PUBLIC` in `.env` (default `5432`). On hosts where that port is taken, set it to something else (e.g. `5437`) — the internal container port is always `5432`.

```bash
# psql via Docker (no host port needed)
docker compose exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# psql from the host
psql -h localhost -p ${POSTGRES_PORT_PUBLIC} -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# Useful queries
# How many states have been recorded?
SELECT COUNT(*) FROM flight_snapshots;

# Most recent snapshot
SELECT * FROM flight_snapshots ORDER BY time DESC LIMIT 5;

# All detected incidents
SELECT icao24, callsign, event_timestamp FROM incident_tracks ORDER BY event_timestamp DESC;
```

---

## Running tests

Tests use an in-memory SQLite database and do not require Docker or a running API.

```bash
uv sync --group dev
uv run python -m pytest tests/ -v
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` | — | PostgreSQL username |
| `POSTGRES_PASSWORD` | — | PostgreSQL password (**required**) |
| `POSTGRES_DB` | — | Database name |
| `POSTGRES_PORT_PUBLIC` | `5432` | Host port exposed to the outside world |
| `POSTGRES_PORT_INTERNAL` | `5432` | Internal container port (rarely needs changing) |
| `DATABASE_URL` | — | Full SQLAlchemy connection URL (**required**) |
| `POLL_INTERVAL` | `300` | Seconds between API polls |
| `OPENSKY_CREDENTIALS` | `credentials.json` | Path to credentials file inside container |
| `LOG_FILE` | `logs/tracker.log` | Log file path inside container |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `GHOST_TIMEOUT` | `1800` | Seconds a normal plane must be missing before triggering |
| `GHOST_MIN_POLLS` | `3` | Minimum poll cycles a plane must be confirmed before ghost-tracking |
| `SPI_TIMEOUT` | `900` | Seconds an SPI-flagged plane must be missing before triggering (default: `GHOST_MIN_POLLS × POLL_INTERVAL`) |

---

## Project structure

```
├── src/
│   ├── config.py          # Environment variable loading
│   ├── database.py        # DB engine, table creation, insert helper
│   ├── incident.py        # Track fetch and storage
│   ├── logging_setup.py   # Rotating file + stdout logging
│   ├── models.py          # SQLModel table definitions
│   └── tracker.py         # Main polling loop and ghost state machine
├── tests/                 # pytest suite (SQLite-based)
├── main.py                # Entrypoint
├── Dockerfile
├── docker-compose.yml
├── credentials.json       # OpenSky OAuth2 credentials (not in git)
└── .env                   # Local environment config (not in git)
```

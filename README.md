# Flight Tracker

Polls the [OpenSky Network](https://opensky-network.org/) API every 5 minutes, stores worldwide aircraft states in PostgreSQL, and reactively detects potential mid-air incidents by monitoring for aircraft that disappear above 500 m and stay missing for 10 minutes.

## Prerequisites

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

The PostgreSQL port is exposed on `localhost:5432`.

```bash
# psql via Docker
docker compose exec db psql -U flightdata -d flightdata

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
| `DATABASE_URL` | — | Full SQLAlchemy connection URL (**required**) |
| `POLL_INTERVAL` | `300` | Seconds between API polls |
| `OPENSKY_CREDENTIALS` | `credentials.json` | Path to credentials file inside container |
| `LOG_FILE` | `logs/tracker.log` | Log file path inside container |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

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

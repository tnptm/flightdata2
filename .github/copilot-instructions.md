# GitHub Copilot Instructions — flightdata2

## Project overview

Python 3.14 service that polls the OpenSky Network ADS-B API every 5 minutes,
stores worldwide aircraft states to PostgreSQL, and reactively detects potential
mid-air incidents by tracking aircraft that disappear under specific conditions.
Deployed with Docker Compose. Tested with SQLite-backed pytest.

---

## Stack and tooling

| Concern | Tool |
|---|---|
| Python version | 3.14 (`requires-python = ">=3.14"`) |
| Package manager | `uv` — use `uv sync --group dev` for dev deps |
| ORM | SQLModel + SQLAlchemy |
| Database (prod) | PostgreSQL 18 |
| Database (tests) | SQLite via `tmp_path` fixture |
| DataFrame processing | polars |
| ADS-B data source | `opensky-api` (VCS install from GitHub) |
| Linter | ruff — always run `uv run ruff check` before committing |
| Test runner | `uv run python -m pytest tests/` |

---

## Module structure

```
src/
  config.py         # All env vars loaded with os.environ.get(); never import at module level
  database.py       # Engine singleton (_get_engine), table creation, batch CRUD, bulk insert
  incident.py       # fetch_and_store_track — calls api.get_track_by_aircraft(icao, t=timestamp)
  logging_setup.py  # RotatingFileHandler 10 MB/5 backups + stdout
  models.py         # SQLModel table definitions: FlightBatch, FlightSnapshot, IncidentTrack
  tracker.py        # main_loop, _build_state, _process_ghosts — core detection state machine
tests/
  conftest.py       # db_url fixture (SQLite), make_batch(), make_state()
  test_database.py
  test_ghost_detection.py
  test_incident.py
main.py             # 3-line entrypoint only
```

---

## Database schema

### `flight_batches`
One row per poll cycle.

| Column | Type | Notes |
|---|---|---|
| `id` | PK int | auto |
| `saved_at` | datetime | UTC timestamp of poll |
| `flight_count` | int | number of states in this batch |
| `detection_warning` | text nullable | incident warnings appended with `\n` |

### `flight_snapshots`
One row per aircraft per poll cycle.

| Column | Type |
|---|---|
| `id` | PK int |
| `batch_id` | FK → flight_batches.id (indexed) |
| `icao24` | str(10) |
| `callsign` | str(10) nullable |
| `time` | datetime (UTC) |
| `latitude`, `longitude` | float nullable |
| `baro_altitude` | float nullable (metres) |
| `velocity` | float nullable |
| `heading` | float nullable |
| `on_ground` | bool |
| `squawk` | str(4) nullable |
| `spi` | bool |

### `incident_tracks`
One row per confirmed incident.

| Column | Type |
|---|---|
| `id` | PK int |
| `icao24` | str(10) |
| `callsign` | str(10) nullable |
| `path_data` | JSON (serialised polars DataFrame) |
| `event_timestamp` | datetime (UTC) |

---

## Incident detection logic

### Normal path (timeout-based)
A plane must be seen in **≥ 3 poll cycles** (`GHOST_MIN_POLLS`) before entering the
ghost buffer. After it disappears it must remain missing for **≥ 1800 s / 30 min**
(`GHOST_TIMEOUT`) before evaluation. An incident is triggered only when ALL of:

- `baro_altitude > 500 m` (`INCIDENT_MIN_ALTITUDE`)
- `baro_altitude ≤ 25 000 m` (`INCIDENT_MAX_ALTITUDE`) — above this is treated as sensor glitch
- `on_ground == False`

### Emergency path (immediate)
If the last known state has **squawk `7700`** (general emergency), **`7500`**
(hijack), or **SPI flag** set, both filters are bypassed and the incident triggers
on the same cycle the plane vanishes. Altitude and on-ground rules still apply.

---

## Key conventions

### Engine singleton
`database.py` holds `_engines: dict[str, Engine]`. Always call `_get_engine(url)`
— never `create_engine()` directly. This prevents connection pool exhaustion when
many incidents fire in a single cycle.

### DB function signatures
All public DB functions accept `db_url: str | None = None`. When `None`, they fall
back to `config.DB_URL`. Tests always pass an explicit SQLite URL.

### Bulk insert
Use `log_to_postgres(df: pl.DataFrame, table: str, db_url=None)`. Internally uses
`Table.insert()` via SQLAlchemy core — no pandas dependency.

### Config
All constants live in `src/config.py`. Every value uses `os.environ.get()` so
`DATABASE_URL` stays `None` until a DB call is made (avoids import-time crashes in
tests).

### OpenSky API
- `TokenManager.from_json_file("credentials.json")` for OAuth2
- `api.get_states()` returns all global aircraft states
- `api.get_track_by_aircraft(icao24, t=unix_timestamp)` — parameter is `t=`, NOT `time=`
- `StateVector` fields include: `icao24`, `callsign`, `latitude`, `longitude`,
  `baro_altitude`, `velocity`, `true_track` (heading), `on_ground`, `time_position`,
  `last_contact`, `squawk`, `spi`, `position_source`

### Schema changes
`SQLModel.metadata.create_all(engine)` only creates missing tables — it never
alters existing ones. For schema changes in production, use `docker compose down -v`
(dev) or write manual `ALTER TABLE` statements.

### PostgreSQL 18
Volume must be mounted at `/var/lib/postgresql` — **not** `/var/lib/postgresql/data`
(breaking change in pg18).

---

## Testing conventions

- One `db_url` fixture per test — SQLite file under `tmp_path`, recreated fresh
- `make_batch(db_url)` and `make_state(icao, alt, on_ground, squawk, spi)` helpers in `conftest.py`
- Mock API calls with `mocker.patch("src.tracker.fetch_and_store_track")`
- Never use real network or PostgreSQL in tests

---

## Common commands

```bash
# Install deps (including dev)
uv sync --group dev

# Lint
uv run ruff check

# Run all tests
uv run python -m pytest tests/ -v

# Rebuild only the app container (leave DB running)
docker compose up --build -d --no-deps app

# Full rebuild with DB wipe (schema reset)
docker compose down -v && docker compose up --build -d

# Tail live logs
docker compose logs -f app

# Tail log file on host
tail -f logs/tracker.log
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | Full SQLAlchemy URL (**required**) |
| `POSTGRES_USER` | — | PostgreSQL username |
| `POSTGRES_PASSWORD` | — | PostgreSQL password |
| `POSTGRES_DB` | — | Database name |
| `POSTGRES_PORT_PUBLIC` | `5432` | Host port (override if 5432 is taken) |
| `POSTGRES_PORT_INTERNAL` | `5432` | Internal container port |
| `POLL_INTERVAL` | `300` | Seconds between API polls |
| `OPENSKY_CREDENTIALS` | `credentials.json` | Path to credentials file in container |
| `GHOST_TIMEOUT` | `1800` | Seconds missing before triggering |
| `GHOST_MIN_POLLS` | `3` | Min polls confirmed before ghost-tracking |
| `LOG_FILE` | `logs/tracker.log` | Log file path in container |
| `LOG_LEVEL` | `INFO` | Logging level |

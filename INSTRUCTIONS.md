This is a comprehensive development guide for your **Global Flight Surveillance & Incident Tracker**. You can save this content as `INSTRUCTIONS.md` in your project folder.

---

# ✈️ Project: Reactive Flight Tracker (OpenSky + PostgreSQL)

This project implements a high-efficiency global flight monitoring system. It logs worldwide aircraft states every 5 minutes and uses a **Reactive State Machine** to trigger high-resolution track captures only when a flight disappears mid-air (potential incident).

## 🛠 Tech Stack

* **Language:** Python 3.12+
* **Package Manager:** `uv`
* **API:** OpenSky Network (Standard Tier - 4,000 credits/day)
* **Data Processing:** `polars`
* **Database:** PostgreSQL + SQLAlchemy
* **Authentication:** OAuth2 (Client Credentials Flow)

---

## 1. Environment Setup

Using `uv` for high-performance dependency management:

```bash
# Initialize project
uv init
uv add opensky-api polars sqlalchemy psycopg2-binary

```

### 🔑 Credentials

Create a `credentials.json` file in the root directory:

```json
{
    "clientId": "your_client_id",
    "clientSecret": "your_client_secret"
}

```

> **Security Note:** Add `credentials.json` and `*.parquet` to your `.gitignore`.

---

## 2. Database Schema

Execute the following in your PostgreSQL instance:

```sql
-- Global snapshots (every 5 minutes)
CREATE TABLE flight_snapshots (
    id SERIAL PRIMARY KEY,
    icao24 VARCHAR(10),
    callsign VARCHAR(10),
    time TIMESTAMP WITH TIME ZONE,
    latitude FLOAT,
    longitude FLOAT,
    baro_altitude FLOAT,
    velocity FLOAT,
    heading FLOAT,
    on_ground BOOLEAN
);

-- Targeted incident paths (Reactive triggers)
CREATE TABLE incident_tracks (
    id SERIAL PRIMARY KEY,
    icao24 VARCHAR(10),
    callsign VARCHAR(10),
    path_data JSONB, -- Stores the full trajectory
    event_timestamp TIMESTAMP WITH TIME ZONE
);

```

---

## 3. The Reactive Model Logic

To stay within the 4,000 daily credit limit, the app follows this mathematical constraint:

* **Global Scan Cost:** 4 credits per call.
* **Interval:** 300 seconds (5 mins) = 12 calls/hour.
* **Daily Base Cost:** $12 \times 24 \times 4 = 1,152 \text{ credits}$.
* **Remaining Budget:** $\approx 2,848 \text{ credits}$ for incident track captures.

### State Machine Workflow:

1. **State Update:** Fetch `/states/all`, log to `flight_snapshots`.
2. **Ghost Detection:** If a plane existed in $T_{-1}$ but is missing in $T_{0}$, move it to a "Ghost" buffer.
3. **Trigger:** If a "Ghost" stays missing for 10 minutes AND its last altitude was $> 500m$, trigger a `/tracks/all` request.
4. **Storage:** Save the detailed path to `incident_tracks`.

---

## 4. Implementation Code (`main.py`)

```python
import time
import polars as pl
from datetime import datetime, timezone
from sqlalchemy import create_engine
from opensky_api import OpenSkyApi, TokenManager

# Configuration
DB_URL = "postgresql://user:password@localhost:5432/flight_db"
tm = TokenManager.from_json_file("credentials.json")
api = OpenSkyApi(token_manager=tm)

# Memory for Reactive Trigger
last_known_states = {} # {icao24: dict_data}
ghosts = {} # {icao24: disappeared_at_timestamp}

def log_to_postgres(df, table):
    df.write_database(table_name=table, connection=DB_URL, if_table_exists="append")

def fetch_and_store_track(icao, last_time):
    try:
        track = api.get_track_by_aircraft(icao, time=last_time)
        if track and track.path:
            # Efficiently map the Waypoint objects via __dict__
            df_track = pl.DataFrame([p.__dict__ for p in track.path])
            
            # Store as JSONB for analysis
            incident_df = pl.DataFrame({
                "icao24": [icao],
                "callsign": [track.callsign],
                "path_data": [df_track.to_init_repr()], # Or df.write_json()
                "event_timestamp": [datetime.fromtimestamp(last_time, tz=timezone.utc)]
            })
            log_to_postgres(incident_df, "incident_tracks")
    except Exception as e:
        print(f"Track Fetch Error: {e}")

def main_loop():
    while True:
        response = api.get_states()
        if not response: continue
        
        now = int(time.time())
        current_icaos = set()
        
        # Process Snapshots
        states_list = []
        for s in response.states:
            icao = s.icao24
            current_icaos.add(icao)
            
            state_dict = {
                "icao24": icao,
                "callsign": s.callsign.strip(),
                "time": datetime.fromtimestamp(s.time_position or s.last_contact, tz=timezone.utc),
                "latitude": s.latitude,
                "longitude": s.longitude,
                "baro_altitude": s.baro_altitude,
                "on_ground": s.on_ground
            }
            states_list.append(state_dict)
            last_known_states[icao] = state_dict

        # Bulk Insert Snapshots
        pl.DataFrame(states_list).write_database("flight_snapshots", DB_URL, if_table_exists="append")

        # Handle Reactive Triggers (Ghosts)
        for icao in list(last_known_states.keys()):
            if icao not in current_icaos:
                # Disappearance logic
                last_state = last_known_states[icao]
                if last_state["baro_altitude"] and last_state["baro_altitude"] > 500:
                    fetch_and_store_track(icao, int(last_state["time"].timestamp()))
                del last_known_states[icao]

        time.sleep(300)

if __name__ == "__main__":
    main_loop()

```

---

## 5. Analytics Queries

Once your data is flowing, you can run these in Postgres:

**Find the busiest 5-minute window in history:**

```sql
SELECT time, COUNT(*) as plane_count 
FROM flight_snapshots 
GROUP BY time 
ORDER BY plane_count DESC LIMIT 1;

```

**Find potential emergency descents:**

```sql
-- Select planes that dropped more than 2000m between two snapshots
-- (Requires Window Functions)
SELECT icao24, baro_altitude, 
       LAG(baro_altitude) OVER (PARTITION BY icao24 ORDER BY time) - baro_altitude as drop_rate
FROM flight_snapshots;

```

---

## 🚀 Getting Started

1. Install dependencies: `uv sync`.
2. Configure `DB_URL` and `credentials.json`.
3. Run: `python main.py`.
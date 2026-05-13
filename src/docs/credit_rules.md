In 2026, the OpenSky Network API uses a **multi-bucket credit system**. This is a crucial distinction: your usage is not tracked as one giant pool, but as three independent "wallets." Spending credits on state vectors does not deplete your ability to fetch tracks.

Here is the breakdown of how different API calls consume credits and how the buckets work.

### 1. The Independent Bucket System

OpenSky tracks your quota in three separate, independent categories. Each category has its own daily limit (e.g., **4,000 credits per day** for a standard user).

| Bucket | Endpoints Included |
| --- | --- |
| **`/states/`** | `/states/all`, `/states/own` |
| **`/tracks/`** | `/tracks/all`, `/tracks/aircraft` |
| **`/flights/`** | `/flights/all`, `/flights/aircraft`, `/flights/arrival`, `/flights/departure` |

> **Key Rule:** If you use all 4,000 credits in the **States** bucket, you still have 4,000 credits available in the **Tracks** bucket and 4,000 in the **Flights** bucket.

---

### 2. Credit Cost per Request

The cost of a single request depends on **how far back in time** you are looking.

| Data Time Range (Partition) | Credit Cost per Request |
| --- | --- |
| **Live / Recent (< 24 hours)** | **4 Credits** |
| **1 – 2 Days Ago** | **30 Credits** |
| **3 – 10 Days Ago** | **60 × N** (where N = number of days) |
| **Historical (> 25 Days)** | **960 × N** |

* **States API (`/states/all`):** Almost always costs **4 credits** because you are typically pulling live data for your monitor.
* **Tracks API (`/tracks/all`):** If you pull a track for a flight happening *now* or today, it costs **4 credits**. If you pull a track for a flight that happened 3 days ago, the cost jumps significantly.
* **Exceptions:** The endpoint `/states/own` is **free (0 credits)** and does not count against your quota.

---

### 3. Daily Quotas (Per Bucket)

Your "Standard User" tier gives you 4,000 credits **per bucket, per day**.

| User Tier | Daily Credits (per bucket) | Refill Frequency |
| --- | --- | --- |
| **Anonymous** | 400 | Daily |
| **Standard User** | **4,000** | **Daily** |
| **Active Feeder** | 8,000 | Daily |
| **Licensed User** | 14,400 | **Hourly** |

---

### 4. Practical Math for Your Project

Since you are planning to log states every 5 minutes and fetch tracks reactively:

* **State Logs:** 12 calls per hour × 24 hours = 288 calls.
* $288 \times 4 \text{ credits} = \mathbf{1,152}$ **credits/day** (from the **States** bucket).
* *You are well within your 4,000 limit.*


* **Incident Tracks:** Since these use a separate bucket, you have a full **4,000 credits/day** just for tracks.
* At 4 credits per live track, you could trigger **1,000 incidents per day** before hitting the limit in the Tracks bucket.


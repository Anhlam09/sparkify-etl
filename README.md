# Sparkify: Data Modeling with PostgreSQL + Python ETL

Sparkify is a (fictional) music streaming startup. Its data lives in two sets
of JSON files: song metadata and user activity logs. In that form, you can't
easily answer questions like "what songs are users listening to?".

**What we did:** designed a **star schema** in PostgreSQL that is built for
song-play analysis. We also built an **ETL pipeline** in Python that extracts
the JSON files, cleans and reshapes them with pandas, and loads them into that
schema. We then checked the loaded data and ran example analytics queries.

**Result:** 150 raw JSON files (11,124 log events) became a clean, queryable
database of 8,820 song plays. There are no orphaned rows, and re-running the
pipeline creates no duplicates. See [Results](#results).

---

## Project structure

| File | Purpose |
|---|---|
| `generate_data.py` | Step 1: generates a sample dataset in the original Sparkify format under `data/` |
| `sql_queries.py` | All SQL: `CREATE`/`DROP` statements, inserts, and the song lookup query |
| `create_tables.py` | Step 2: drops and recreates the `sparkifydb` database and all tables |
| `etl.py` | Step 3: extracts the JSON files, transforms them with pandas and loads them into Postgres |
| `test_queries.py` | Step 4: data-quality checks and example analytics queries |
| `db.py` | Connection settings (env vars with local defaults) |
| `sparkify_etl.py` | All four steps in one self-contained script |

---

## The steps, explained

### Step 1: Get the raw data (`generate_data.py`)

The pipeline reads two datasets that use the original Sparkify file layout:

- **Song data:** `data/song_data/A/B/C/TRABC*.json`. There is one JSON object per file, holding a song and its artist. Files are partitioned by the first three letters of the track ID.
- **Log data:** `data/log_data/2018/11/2018-11-DD-events.json`. These are newline-delimited app events, one file per day, for November 2018. Each event is a page view such as `NextSong`, `Home` or `Upgrade`, along with the user, session, timestamp and browser.

`generate_data.py` creates a realistic sample of both datasets: 120 songs by 40
artists, and 30 days of activity from 60 users. It is seeded, so the results are
reproducible. It deliberately includes the messiness of the real data:

- non-song events
- logged-out events with an empty `userId`
- songs with an unknown year (`0`)
- artists with no location
- users who upgrade from free to paid partway through the month
- plays of songs that aren't in the song catalogue

If you have the real Sparkify dataset, put it in `data/` and skip this step.

### Step 2: Design the schema and create the tables (`sql_queries.py`, `create_tables.py`)

We chose a **star schema**. Every analytics question is about song plays, so
song plays become the central **fact table**. The details describing each play
(who, what, by whom, when) go into small **dimension tables**:

```
                 ┌──────────────┐
                 │    users     │
                 │ user_id (PK) │
                 └──────┬───────┘
┌──────────────┐ ┌──────┴────────────┐ ┌────────────────┐
│    time      ├─┤    songplays      ├─┤    artists     │
│start_time(PK)│ │ songplay_id (PK)  │ │ artist_id (PK) │
└──────────────┘ │ start_time  (FK)  │ └───────┬────────┘
                 │ user_id     (FK)  │         │
                 │ song_id     (FK)  ├─┐ ┌─────┴────────┐
                 │ artist_id   (FK)  │ └─┤    songs     │
                 │ level, session_id │   │ song_id (PK) │
                 │ location, agent   │   │ artist_id(FK)│
                 └───────────────────┘   └──────────────┘
```

| Table | Type | Columns |
|---|---|---|
| `songplays` | Fact: one row per song play | `songplay_id, start_time, user_id, level, song_id, artist_id, session_id, location, user_agent` |
| `users` | Dimension | `user_id, first_name, last_name, gender, level` |
| `songs` | Dimension | `song_id, title, artist_id, year, duration` |
| `artists` | Dimension | `artist_id, name, location, latitude, longitude` |
| `time` | Dimension | `start_time, hour, day, week, month, year, weekday` |

**Why a star schema?** Any question becomes "the fact table plus one join per
dimension". This keeps queries simple to write and fast to run, and
aggregations such as plays per hour, per level or per artist are
straightforward.

`create_tables.py` drops and recreates the `sparkifydb` database. It then
creates the dimension tables before the fact table, so the foreign keys resolve.
The tables enforce data integrity:

- primary keys on every table
- foreign keys from `songplays` to each dimension
- `NOT NULL` on required columns
- `UNIQUE (start_time, user_id, session_id)` on `songplays`, which blocks duplicate plays

### Step 3: Run the ETL (`etl.py`)

The ETL runs in two passes. Songs are loaded first, so log events can look them up.

**Pass 1: song files → `artists`, `songs`**
1. Read each song JSON file with pandas.
2. Select the artist columns and turn empty locations into `NULL`. Insert into `artists`.
3. Select the song columns and turn `year = 0` ("unknown") into `NULL`. Insert into `songs`.

**Pass 2: log files → `time`, `users`, `songplays`**
1. Read each day's log file and **keep only `page == "NextSong"` events**, which are the actual song plays. This drops page views and logged-out events.
2. **`time`:** convert the millisecond `ts` into a timestamp and split it into hour, day, ISO week, month, year and weekday.
3. **`users`:** keep each user's *most recent* event, so that `level` (free or paid) reflects their current subscription.
4. **`songplays`:** logs contain only the song title, artist name and song length. They don't contain IDs. To get `song_id` and `artist_id`, we look up each play in `songs` joined with `artists`, matching on all three fields. Duration is compared with a small float tolerance. If a song isn't in the catalogue, its IDs are left `NULL`, but the play is still recorded.

**How the loading works:**
- **Idempotent upserts:** every insert uses `ON CONFLICT`, so re-running the ETL is safe. The `users` insert updates `level` on conflict, so a user who upgrades is shown as `paid`.
- **Bulk inserts:** rows are batched with `psycopg2.extras.execute_values` instead of being inserted one at a time.
- **Per-file transactions:** each file is committed on its own. If a file fails, its changes are rolled back and the error is reported with the file name.

### Step 4: Validate and analyze (`test_queries.py`)

This step runs data-quality checks (row counts, song-match rate, orphaned rows)
and four example analytics queries. The output is shown below.

---

## Results

These results come from running the full pipeline on the generated sample dataset.

### What was loaded

| Input | Count |
|---|---|
| Song files | 120 |
| Log files (days) | 30 |
| Raw log events | 11,124 |
| `NextSong` events kept | 8,820 |
| Non-song events dropped (`Home`, `Upgrade`, `Settings`, …) | 2,304 |

| Table | Rows |
|---|---|
| `songplays` | 8,820 |
| `users` | 60 |
| `songs` | 120 |
| `artists` | 39 |
| `time` | 8,803 |

- `time` has slightly fewer rows than `songplays` because some plays share the same timestamp.
- `artists` has 39 rows, not 40, because one generated artist was never assigned a song.

### Data-quality checks

| Check | Result |
|---|---|
| Song plays matched to a catalogue song | **3,017 of 8,820 (34%)**. This matches the ~35% the generator plays from the catalogue. The rest are songs that aren't in the song dataset. |
| Orphaned song plays (no matching user or time row) | **0** |
| Re-running `etl.py` a second time | Row counts unchanged (**no duplicates**) |

### Example analytics

**Top 5 most-played songs**

| Title | Artist | Plays |
|---|---|---|
| Love | The Electric Project | 49 |
| Paper | Ava Hall | 43 |
| Electric Neon Stars | The Neon Kids | 39 |
| Fire Rain | The Paper Kids | 39 |
| River | The Mirror Project | 37 |

**Plays by subscription level:** free users account for 5,119 plays (58%) and paid users for 3,701 (42%).

**Busiest hours (UTC):** 01:00 (507 plays), 23:00 (488), 07:00 (449), 02:00 (434), 11:00 (428).

**Most active users:** Caleb Chen (paid, 232 plays), Noah Young (free, 212), Eli Clark (free, 208).

All the names and songs above are synthetic data from `generate_data.py`.

---

## How to run

Requires Python 3 and a running PostgreSQL server.

```bash
pip install -r requirements.txt
python generate_data.py   # Step 1: create sample JSON data (skip if you have the real dataset in data/)
python create_tables.py   # Step 2: create sparkifydb + tables
python etl.py             # Step 3: load data
python test_queries.py    # Step 4: verify + run example analytics
```

Or run all four steps at once:

```bash
python sparkify_etl.py
```

Connection settings come from `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`
and `SPARKIFY_DB`. The defaults are `localhost`, `5432`, your OS user, no
password and `sparkifydb`.

## Example queries

```sql
-- Most played songs
SELECT s.title, a.name, COUNT(*) AS plays
FROM songplays sp
JOIN songs s   ON sp.song_id = s.song_id
JOIN artists a ON sp.artist_id = a.artist_id
GROUP BY s.title, a.name ORDER BY plays DESC LIMIT 5;

-- Free vs paid listening
SELECT level, COUNT(*) FROM songplays GROUP BY level;

-- Busiest hours
SELECT t.hour, COUNT(*) FROM songplays sp
JOIN time t ON sp.start_time = t.start_time
GROUP BY t.hour ORDER BY 2 DESC;
```

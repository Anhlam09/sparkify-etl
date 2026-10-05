# Sparkify: Data Modeling with PostgreSQL + Python ETL

Sparkify is a (fictional) music streaming startup. Its data lives in two sets
of JSON files: song metadata and user activity logs. Neither is easy to query
as-is. This project designs a **star schema** in PostgreSQL that is optimized
for song-play analysis and builds an **ETL pipeline** in Python that loads
the JSON files into it.

## Project structure

| File | Purpose |
|---|---|
| `generate_data.py` | Generates a sample dataset in the original Sparkify format under `data/` |
| `sql_queries.py` | All SQL: `CREATE`/`DROP` statements, inserts, and the song lookup query |
| `create_tables.py` | Drops and recreates the `sparkifydb` database and all tables |
| `etl.py` | Extracts JSON files, transforms them with pandas, loads them into Postgres |
| `test_queries.py` | Data-quality checks and example analytics queries |
| `db.py` | Connection settings (env vars with local defaults) |

## Datasets

- **Song data:** `data/song_data/A/B/C/TRABC*.json`. One song per file, with song and artist metadata.
- **Log data:** `data/log_data/2018/11/2018-11-DD-events.json`. Newline-delimited app events (one file per day). Only `page == "NextSong"` events are song plays.

## Schema (star schema)

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

**Fact table**
- `songplays`: one row per song play: `songplay_id, start_time, user_id, level, song_id, artist_id, session_id, location, user_agent`

**Dimension tables**
- `users`: `user_id, first_name, last_name, gender, level`
- `songs`: `song_id, title, artist_id, year, duration`
- `artists`: `artist_id, name, location, latitude, longitude`
- `time`: `start_time, hour, day, week, month, year, weekday`

### Why a star schema?
The analytics team's questions are all about song plays ("what's played most?",
"when?", "by free or paid users?"). A central fact table joined to small,
denormalized dimensions keeps these queries simple (one join per dimension) and
fast, and makes aggregations straightforward.

### Design decisions
- **Upserts:** every insert uses `ON CONFLICT`. Re-running the ETL is idempotent, and `users.level` is updated to the latest value, because users can upgrade from free to paid.
- **Song matching:** logs only contain song title, artist name and length. `songplays.song_id`/`artist_id` are found by matching all three (duration with a float tolerance) and are `NULL` when the song isn't in the catalogue.
- **Integrity:** foreign keys from `songplays` to every dimension, `NOT NULL` on required columns, and a `UNIQUE (start_time, user_id, session_id)` on `songplays` to prevent duplicates.
- **Bulk loading:** rows are inserted with `psycopg2.extras.execute_values`, and each file is committed as a transaction (rolled back on error).

## How to run

Requires Python 3 and a running PostgreSQL server.

```bash
pip install -r requirements.txt
python generate_data.py   # create sample JSON data (skip if you have the real dataset in data/)
python create_tables.py   # create sparkifydb + tables
python etl.py             # load data
python test_queries.py    # verify + run example analytics
```

Connection settings come from `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`
and `SPARKIFY_DB` (defaults: localhost, 5432, your OS user, no password, `sparkifydb`).

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

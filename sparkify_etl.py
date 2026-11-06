"""Sparkify: Data Modeling with PostgreSQL + Python ETL (single-file version).

Steps, run in order by main():
  1. Generate sample JSON song + log data in ./data (skipped if it exists)
  2. (Re)create the sparkifydb database and star-schema tables
  3. ETL: extract JSON files, transform with pandas, load into Postgres
  4. Run data-quality checks and example analytics queries

Usage:  python3 sparkify_etl.py
Connection: PGHOST, PGPORT, PGUSER, PGPASSWORD, SPARKIFY_DB env vars
(defaults: localhost, 5432, your OS user, no password, sparkifydb).
"""
import getpass
import glob
import json
import os
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import AsIs, register_adapter
from psycopg2.extras import execute_values

random.seed(42)
DATA = Path(__file__).parent / "data"

# Let psycopg2 accept numpy scalars coming out of pandas
register_adapter(np.int64, AsIs)
register_adapter(np.float64, AsIs)


# ======================================================================
# 1. SAMPLE DATA GENERATION
# ======================================================================

WORDS = ("love night city fire dream heart summer rain gold blue river road "
         "electric echo shadow light wild young midnight ocean stars velvet "
         "neon broken silver home ghost thunder sugar paper mirror").split()
CITIES = ["New York, NY", "Los Angeles, CA", "Chicago, IL", "Austin, TX",
          "Seattle, WA", "Atlanta, GA", "Denver, CO", "Boston, MA",
          "San Francisco-Oakland-Hayward, CA", "Portland-South Portland, ME"]
FIRST = ["Ava", "Liam", "Mia", "Noah", "Zoe", "Ethan", "Lily", "Mason", "Chloe",
         "Lucas", "Ella", "Logan", "Aria", "Jacob", "Nora", "Owen", "Ivy",
         "Caleb", "Ruby", "Henry", "Jade", "Leo", "Maya", "Eli", "Kai"]
LAST = ["Smith", "Garcia", "Kim", "Nguyen", "Patel", "Brown", "Lopez", "Chen",
        "Davis", "Wilson", "Moore", "Clark", "Lewis", "Young", "Hall"]
AGENTS = [
    '"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.143 Safari/537.36"',
    '"Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.143 Safari/537.36"',
    "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:31.0) Gecko/20100101 Firefox/31.0",
    '"Mozilla/5.0 (iPhone; CPU iPhone OS 7_1_2 like Mac OS X) AppleWebKit/537.51.2 (KHTML, like Gecko) Version/7.0 Mobile/11D257 Safari/9537.53"',
]


def rand_id(prefix, n=16):
    return prefix + "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def title(k):
    return " ".join(random.sample(WORDS, k)).title()


def make_songs(n_artists=40, n_songs=120):
    artists = []
    for _ in range(n_artists):
        has_geo = random.random() < 0.6
        artists.append({
            "artist_id": rand_id("AR"),
            "artist_name": f"The {title(1)} {random.choice(['Band', 'Collective', 'Project', 'Kids', 'Society'])}"
                           if random.random() < 0.5 else f"{random.choice(FIRST)} {random.choice(LAST)}",
            "artist_location": random.choice(CITIES + [""]),
            "artist_latitude": round(random.uniform(25, 48), 5) if has_geo else None,
            "artist_longitude": round(random.uniform(-122, -71), 5) if has_geo else None,
        })
    songs = []
    for _ in range(n_songs):
        a = random.choice(artists)
        track_id = "TRA" + "".join(random.choices(string.ascii_uppercase, k=2)) + rand_id("", 13)
        song = {"num_songs": 1, **a,
                "song_id": rand_id("SO"),
                "title": title(random.randint(1, 3)),
                "duration": round(random.uniform(120, 420), 5),
                "year": random.choice([0] + list(range(1970, 2011)))}
        path = DATA / "song_data" / track_id[2] / track_id[3] / track_id[4] / f"{track_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(song))
        songs.append(song)
    return songs


def make_logs(songs, n_users=60, days=30):
    users = [{"userId": str(i), "firstName": random.choice(FIRST), "lastName": random.choice(LAST),
              "gender": random.choice("MF"), "level": random.choice(["free", "free", "paid"]),
              "location": random.choice(CITIES), "userAgent": random.choice(AGENTS),
              "registration": float(random.randint(1_530_000_000_000, 1_541_000_000_000))}
             for i in range(1, n_users + 1)]
    other_pages = ["Home", "Logout", "Settings", "Help", "About", "Upgrade", "Downgrade"]
    session_id = 1
    for d in range(days):
        day = datetime(2018, 11, 1) + timedelta(days=d)
        events = []
        for u in random.sample(users, random.randint(15, 35)):
            # Users upgrade from free to paid over the month
            if u["level"] == "free" and random.random() < 0.03:
                u["level"] = "paid"
            t = day + timedelta(seconds=random.randint(0, 80_000))
            for item in range(random.randint(3, 25)):
                is_song = random.random() < 0.8
                if is_song:
                    # ~35% of plays are songs present in our song catalogue;
                    # the rest come from the much larger full catalogue
                    s = random.choice(songs) if random.random() < 0.35 else {
                        "artist_name": f"{random.choice(FIRST)} {random.choice(LAST)}",
                        "title": title(2), "duration": round(random.uniform(120, 420), 5)}
                events.append({
                    "artist": s["artist_name"] if is_song else None,
                    "auth": "Logged In",
                    "firstName": u["firstName"], "gender": u["gender"],
                    "itemInSession": item, "lastName": u["lastName"],
                    "length": s["duration"] if is_song else None,
                    "level": u["level"], "location": u["location"],
                    "method": "PUT" if is_song else "GET",
                    "page": "NextSong" if is_song else random.choice(other_pages),
                    "registration": u["registration"], "sessionId": session_id,
                    "song": s["title"] if is_song else None,
                    "status": 200,
                    "ts": int(t.timestamp() * 1000),
                    "userAgent": u["userAgent"], "userId": u["userId"],
                })
                t += timedelta(seconds=random.randint(60, 400))
            session_id += 1
        # A few logged-out events with empty userId, as in the real logs
        for _ in range(random.randint(2, 6)):
            events.append({"artist": None, "auth": "Logged Out", "firstName": None, "gender": None,
                           "itemInSession": 0, "lastName": None, "length": None, "level": "free",
                           "location": None, "method": "GET", "page": "Home", "registration": None,
                           "sessionId": session_id, "song": None, "status": 200,
                           "ts": int((day + timedelta(seconds=random.randint(0, 86_000))).timestamp() * 1000),
                           "userAgent": None, "userId": ""})
            session_id += 1
        events.sort(key=lambda e: e["ts"])
        path = DATA / "log_data" / "2018" / "11" / f"{day:%Y-%m-%d}-events.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


# ======================================================================
# 2. SQL QUERIES
# ======================================================================

# DROP TABLES

songplay_table_drop = "DROP TABLE IF EXISTS songplays;"
user_table_drop = "DROP TABLE IF EXISTS users;"
song_table_drop = "DROP TABLE IF EXISTS songs;"
artist_table_drop = "DROP TABLE IF EXISTS artists;"
time_table_drop = "DROP TABLE IF EXISTS time;"

# CREATE TABLES
# Dimension tables are created before the fact table so foreign keys resolve.

user_table_create = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INT PRIMARY KEY,
    first_name VARCHAR,
    last_name  VARCHAR,
    gender     CHAR(1),
    level      VARCHAR NOT NULL
);
"""

artist_table_create = """
CREATE TABLE IF NOT EXISTS artists (
    artist_id VARCHAR PRIMARY KEY,
    name      VARCHAR NOT NULL,
    location  VARCHAR,
    latitude  DOUBLE PRECISION,
    longitude DOUBLE PRECISION
);
"""

song_table_create = """
CREATE TABLE IF NOT EXISTS songs (
    song_id   VARCHAR PRIMARY KEY,
    title     VARCHAR NOT NULL,
    artist_id VARCHAR NOT NULL REFERENCES artists (artist_id),
    year      INT,
    duration  DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS songs_title_idx ON songs (title);
"""

time_table_create = """
CREATE TABLE IF NOT EXISTS time (
    start_time TIMESTAMP PRIMARY KEY,
    hour       SMALLINT NOT NULL,
    day        SMALLINT NOT NULL,
    week       SMALLINT NOT NULL,
    month      SMALLINT NOT NULL,
    year       SMALLINT NOT NULL,
    weekday    SMALLINT NOT NULL
);
"""

songplay_table_create = """
CREATE TABLE IF NOT EXISTS songplays (
    songplay_id SERIAL PRIMARY KEY,
    start_time  TIMESTAMP NOT NULL REFERENCES time (start_time),
    user_id     INT NOT NULL REFERENCES users (user_id),
    level       VARCHAR NOT NULL,
    song_id     VARCHAR REFERENCES songs (song_id),
    artist_id   VARCHAR REFERENCES artists (artist_id),
    session_id  INT NOT NULL,
    location    VARCHAR,
    user_agent  TEXT,
    UNIQUE (start_time, user_id, session_id)
);
"""

# INSERT RECORDS
# Each statement takes a list of tuples via psycopg2.extras.execute_values.

songplay_table_insert = """
INSERT INTO songplays (start_time, user_id, level, song_id, artist_id,
                       session_id, location, user_agent)
VALUES %s
ON CONFLICT (start_time, user_id, session_id) DO NOTHING;
"""

# A user's level can change (free -> paid), so keep the latest value.
user_table_insert = """
INSERT INTO users (user_id, first_name, last_name, gender, level)
VALUES %s
ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level;
"""

song_table_insert = """
INSERT INTO songs (song_id, title, artist_id, year, duration)
VALUES %s
ON CONFLICT (song_id) DO NOTHING;
"""

artist_table_insert = """
INSERT INTO artists (artist_id, name, location, latitude, longitude)
VALUES %s
ON CONFLICT (artist_id) DO NOTHING;
"""

time_table_insert = """
INSERT INTO time (start_time, hour, day, week, month, year, weekday)
VALUES %s
ON CONFLICT (start_time) DO NOTHING;
"""

# FIND SONGS
# The log only has song title, artist name and length, so match on all three
# to recover song_id and artist_id. Duration is compared with a tolerance
# because it is a float.

song_select = """
SELECT s.song_id, a.artist_id
FROM songs s
JOIN artists a ON s.artist_id = a.artist_id
WHERE s.title = %s
  AND a.name = %s
  AND ABS(s.duration - %s) < 0.001
LIMIT 1;
"""

# QUERY LISTS

create_table_queries = [user_table_create, artist_table_create, song_table_create,
                        time_table_create, songplay_table_create]
drop_table_queries = [songplay_table_drop, user_table_drop, song_table_drop,
                      artist_table_drop, time_table_drop]


# ======================================================================
# 3. DATABASE CONNECTION
# ======================================================================

DB_NAME = os.getenv("SPARKIFY_DB", "sparkifydb")


def connect(dbname=DB_NAME):
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", getpass.getuser()),
        password=os.getenv("PGPASSWORD", ""),
        dbname=dbname,
    )


# ======================================================================
# 4. CREATE DATABASE + TABLES
# ======================================================================

def create_database():
    """Drop and recreate the sparkify database; return a connection to it."""
    conn = connect("postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB_NAME)))
    cur.execute(sql.SQL("CREATE DATABASE {} WITH ENCODING 'utf8' TEMPLATE template0")
                .format(sql.Identifier(DB_NAME)))
    conn.close()

    conn = connect(DB_NAME)
    return conn, conn.cursor()


def drop_tables(cur, conn):
    for query in drop_table_queries:
        cur.execute(query)
    conn.commit()


def create_tables(cur, conn):
    for query in create_table_queries:
        cur.execute(query)
    conn.commit()


def run_create_tables():
    conn, cur = create_database()
    drop_tables(cur, conn)
    create_tables(cur, conn)
    conn.close()
    print(f"Created database '{DB_NAME}' with tables: songplays, users, songs, artists, time")


# ======================================================================
# 5. ETL PIPELINE
# ======================================================================


def to_rows(df):
    """DataFrame -> list of tuples with NaN/NaT replaced by None."""
    return [tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)]


def process_song_file(cur, filepath):
    """Load one song file into the artists and songs tables."""
    df = pd.read_json(filepath, lines=True)

    artist_df = df[["artist_id", "artist_name", "artist_location",
                    "artist_latitude", "artist_longitude"]]
    artist_df = artist_df.replace({"artist_location": {"": None}})
    execute_values(cur, artist_table_insert, to_rows(artist_df))

    song_df = df[["song_id", "title", "artist_id", "year", "duration"]]
    song_df = song_df.replace({"year": {0: None}})  # 0 means "unknown year"
    execute_values(cur, song_table_insert, to_rows(song_df))


def process_log_file(cur, filepath):
    """Load one day of event logs into the time, users and songplays tables."""
    df = pd.read_json(filepath, lines=True, convert_dates=False)

    # Only song plays are of interest
    df = df[df["page"] == "NextSong"].copy()
    if df.empty:
        return
    df["start_time"] = pd.to_datetime(df["ts"], unit="ms")
    df["userId"] = df["userId"].astype(int)

    t = df["start_time"]
    time_df = pd.DataFrame({
        "start_time": t,
        "hour": t.dt.hour,
        "day": t.dt.day,
        "week": t.dt.isocalendar().week.astype(int),
        "month": t.dt.month,
        "year": t.dt.year,
        "weekday": t.dt.weekday,
    }).drop_duplicates("start_time")
    time_rows = [(ts.to_pydatetime(), *rest) for ts, *rest in to_rows(time_df)]
    execute_values(cur, time_table_insert, time_rows)

    # Keep each user's most recent record so level reflects their latest status
    user_df = (df.sort_values("ts")
                 .drop_duplicates("userId", keep="last")
                 [["userId", "firstName", "lastName", "gender", "level"]])
    execute_values(cur, user_table_insert, to_rows(user_df))

    songplay_rows = []
    for row in df.itertuples(index=False):
        cur.execute(song_select, (row.song, row.artist, row.length))
        match = cur.fetchone()
        song_id, artist_id = match if match else (None, None)
        songplay_rows.append((row.start_time.to_pydatetime(), row.userId, row.level,
                              song_id, artist_id, row.sessionId, row.location,
                              row.userAgent))
    execute_values(cur, songplay_table_insert, songplay_rows)


def process_data(cur, conn, filepath, func):
    """Run func over every JSON file under filepath, committing per file."""
    all_files = sorted(glob.glob(os.path.join(filepath, "**", "*.json"), recursive=True))
    print(f"{len(all_files)} files found in {filepath}")

    for i, datafile in enumerate(all_files, 1):
        try:
            func(cur, datafile)
            conn.commit()
        except Exception:
            conn.rollback()
            print(f"Failed on {datafile}")
            raise
        if i % 25 == 0 or i == len(all_files):
            print(f"  {i}/{len(all_files)} files processed")


def run_etl():
    conn = connect()
    cur = conn.cursor()
    base = str(DATA)

    # Songs/artists first so songplays can look them up
    process_data(cur, conn, os.path.join(base, "song_data"), process_song_file)
    process_data(cur, conn, os.path.join(base, "log_data"), process_log_file)

    conn.close()


# ======================================================================
# 6. DATA CHECKS + ANALYTICS
# ======================================================================

CHECKS = {
    "row counts": """
        SELECT 'songplays' AS tbl, COUNT(*) FROM songplays UNION ALL
        SELECT 'users', COUNT(*) FROM users UNION ALL
        SELECT 'songs', COUNT(*) FROM songs UNION ALL
        SELECT 'artists', COUNT(*) FROM artists UNION ALL
        SELECT 'time', COUNT(*) FROM time""",
    "songplays with a matched song": """
        SELECT COUNT(*) FILTER (WHERE song_id IS NOT NULL) AS matched,
               COUNT(*) AS total
        FROM songplays""",
    "orphaned songplays (should be 0)": """
        SELECT COUNT(*) FROM songplays sp
        LEFT JOIN users u ON sp.user_id = u.user_id
        LEFT JOIN time t ON sp.start_time = t.start_time
        WHERE u.user_id IS NULL OR t.start_time IS NULL""",
}

ANALYTICS = {
    "Top 5 most-played songs": """
        SELECT s.title, a.name AS artist, COUNT(*) AS plays
        FROM songplays sp
        JOIN songs s ON sp.song_id = s.song_id
        JOIN artists a ON sp.artist_id = a.artist_id
        GROUP BY s.title, a.name
        ORDER BY plays DESC, s.title
        LIMIT 5""",
    "Plays by subscription level": """
        SELECT level, COUNT(*) AS plays,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM songplays GROUP BY level ORDER BY plays DESC""",
    "Busiest hours of the day": """
        SELECT t.hour, COUNT(*) AS plays
        FROM songplays sp JOIN time t ON sp.start_time = t.start_time
        GROUP BY t.hour ORDER BY plays DESC LIMIT 5""",
    "Most active users": """
        SELECT u.first_name || ' ' || u.last_name AS user_name, u.level,
               COUNT(*) AS plays
        FROM songplays sp JOIN users u ON sp.user_id = u.user_id
        GROUP BY u.user_id, user_name, u.level
        ORDER BY plays DESC LIMIT 5""",
}


def run_checks():
    conn = connect()
    for section, queries in (("CHECKS", CHECKS), ("ANALYTICS", ANALYTICS)):
        print(f"\n===== {section} =====")
        for name, q in queries.items():
            with conn.cursor() as cur:
                cur.execute(q)
                df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
            print(f"\n-- {name}\n{df.to_string(index=False)}")
    conn.close()


def main():
    if not DATA.exists():
        make_logs(make_songs())
        print(f"Generated sample data in {DATA}")
    run_create_tables()
    run_etl()
    run_checks()


if __name__ == "__main__":
    main()

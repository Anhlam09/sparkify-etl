"""All SQL used by the project: DDL for the star schema and DML for the ETL."""

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

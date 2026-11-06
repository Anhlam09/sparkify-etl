"""Extract JSON song/log files, transform them with pandas, load into Postgres."""
import glob
import os

import numpy as np
import pandas as pd
from psycopg2.extensions import AsIs, register_adapter
from psycopg2.extras import execute_values

from db import connect
from sql_queries import (artist_table_insert, song_select, song_table_insert,
                         songplay_table_insert, time_table_insert, user_table_insert)

# Let psycopg2 accept numpy scalars coming out of pandas
register_adapter(np.int64, AsIs)
register_adapter(np.float64, AsIs)


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


def main():
    conn = connect()
    cur = conn.cursor()
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    # Songs/artists first so songplays can look them up
    process_data(cur, conn, os.path.join(base, "song_data"), process_song_file)
    process_data(cur, conn, os.path.join(base, "log_data"), process_log_file)

    conn.close()


if __name__ == "__main__":
    main()

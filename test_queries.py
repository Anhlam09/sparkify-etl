"""Sanity checks on the loaded data, plus some example analytics queries."""
import pandas as pd

from db import connect

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


def main():
    conn = connect()
    for section, queries in (("CHECKS", CHECKS), ("ANALYTICS", ANALYTICS)):
        print(f"\n===== {section} =====")
        for name, q in queries.items():
            with conn.cursor() as cur:
                cur.execute(q)
                df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
            print(f"\n-- {name}\n{df.to_string(index=False)}")
    conn.close()


if __name__ == "__main__":
    main()

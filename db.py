"""Connection settings, read from environment variables with local defaults."""
import os
import getpass

import psycopg2

DB_NAME = os.getenv("SPARKIFY_DB", "sparkifydb")


def connect(dbname=DB_NAME):
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", getpass.getuser()),
        password=os.getenv("PGPASSWORD", ""),
        dbname=dbname,
    )

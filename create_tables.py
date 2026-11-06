"""(Re)create the sparkify database and its tables. Run before etl.py."""
from psycopg2 import sql

from db import DB_NAME, connect
from sql_queries import create_table_queries, drop_table_queries


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


def main():
    conn, cur = create_database()
    drop_tables(cur, conn)
    create_tables(cur, conn)
    conn.close()
    print(f"Created database '{DB_NAME}' with tables: songplays, users, songs, artists, time")


if __name__ == "__main__":
    main()

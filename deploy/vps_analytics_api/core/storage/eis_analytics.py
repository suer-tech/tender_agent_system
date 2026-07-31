"""Read-only access to the analytics SQLite database."""
from contextlib import contextmanager
import os
import sqlite3
from pathlib import Path


DB_PATH = Path(os.getenv("ANALYTICS_DB_PATH", Path(__file__).parents[2] / "data" / "eis_analytics.db"))


@contextmanager
def conn():
    connection = sqlite3.connect(f"file:{DB_PATH.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()

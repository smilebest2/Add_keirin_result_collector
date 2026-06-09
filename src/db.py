import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS race_master (
    race_id TEXT PRIMARY KEY,
    race_date TEXT,
    venue TEXT,
    race_no INTEGER,
    detail_url TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS race_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT,
    rank INTEGER,
    car_no INTEGER,
    racer_name TEXT,
    class TEXT,
    prefecture TEXT,
    age INTEGER,
    time TEXT,
    kimarite TEXT,
    FOREIGN KEY (race_id) REFERENCES race_master(race_id)
);

CREATE TABLE IF NOT EXISTS payout (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT,
    bet_type TEXT,
    combination TEXT,
    payout INTEGER,
    FOREIGN KEY (race_id) REFERENCES race_master(race_id)
);
"""


@contextmanager
def connect(db_path: Path = DB_PATH):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def race_exists(conn: sqlite3.Connection, race_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM race_master WHERE race_id = ? LIMIT 1",
        (race_id,),
    ).fetchone()
    return row is not None


def save_race(conn: sqlite3.Connection, race: dict, results: list[dict], payouts: list[dict]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    try:
        conn.execute(
            """
            INSERT INTO race_master
                (race_id, race_date, venue, race_no, detail_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                race["race_id"],
                race["race_date"],
                race["venue"],
                race["race_no"],
                race["detail_url"],
                now,
            ),
        )

        conn.executemany(
            """
            INSERT INTO race_result
                (race_id, rank, car_no, racer_name, class, prefecture, age, time, kimarite)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    race["race_id"],
                    item.get("rank"),
                    item.get("car_no"),
                    item.get("racer_name"),
                    item.get("class"),
                    item.get("prefecture"),
                    item.get("age"),
                    item.get("time"),
                    item.get("kimarite"),
                )
                for item in results
            ],
        )

        conn.executemany(
            """
            INSERT INTO payout
                (race_id, bet_type, combination, payout)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    race["race_id"],
                    item.get("bet_type"),
                    item.get("combination"),
                    item.get("payout"),
                )
                for item in payouts
            ],
        )

        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise

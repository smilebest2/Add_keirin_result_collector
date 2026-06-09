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
    event_name TEXT,
    race_title TEXT,
    race_class TEXT,
    start_time TEXT,
    deadline_time TEXT,
    status TEXT,
    distance INTEGER,
    laps INTEGER,
    weather TEXT,
    temperature REAL,
    wind_direction TEXT,
    wind_speed REAL,
    lineup_text TEXT,
    race_comment TEXT,
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
    term INTEGER,
    margin TEXT,
    time TEXT,
    kimarite TEXT,
    start_mark TEXT,
    back_mark TEXT,
    FOREIGN KEY (race_id) REFERENCES race_master(race_id)
);

CREATE TABLE IF NOT EXISTS payout (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT,
    bet_type TEXT,
    combination TEXT,
    payout INTEGER,
    popularity INTEGER,
    FOREIGN KEY (race_id) REFERENCES race_master(race_id)
);

CREATE TABLE IF NOT EXISTS race_lineup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT,
    car_no INTEGER,
    line_no INTEGER,
    line_position INTEGER,
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
    for column, column_type in {
        "event_name": "TEXT",
        "race_title": "TEXT",
        "race_class": "TEXT",
        "start_time": "TEXT",
        "deadline_time": "TEXT",
        "status": "TEXT",
        "distance": "INTEGER",
        "laps": "INTEGER",
        "weather": "TEXT",
        "temperature": "REAL",
        "wind_direction": "TEXT",
        "wind_speed": "REAL",
        "lineup_text": "TEXT",
        "race_comment": "TEXT",
    }.items():
        ensure_column(conn, "race_master", column, column_type)
    for column, column_type in {
        "term": "INTEGER",
        "margin": "TEXT",
        "start_mark": "TEXT",
        "back_mark": "TEXT",
    }.items():
        ensure_column(conn, "race_result", column, column_type)
    ensure_column(conn, "payout", "popularity", "INTEGER")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


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
                (
                    race_id, race_date, venue, race_no, event_name, race_title,
                    race_class, start_time, deadline_time, status, distance,
                    laps, weather, temperature, wind_direction, wind_speed,
                    lineup_text, race_comment, detail_url, created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                race["race_id"],
                race["race_date"],
                race["venue"],
                race["race_no"],
                race.get("event_name"),
                race.get("race_title"),
                race.get("race_class"),
                race.get("start_time"),
                race.get("deadline_time"),
                race.get("status"),
                race.get("distance"),
                race.get("laps"),
                race.get("weather"),
                race.get("temperature"),
                race.get("wind_direction"),
                race.get("wind_speed"),
                race.get("lineup_text"),
                race.get("race_comment"),
                race["detail_url"],
                now,
            ),
        )

        conn.executemany(
            """
            INSERT INTO race_result
                (
                    race_id, rank, car_no, racer_name, class, prefecture,
                    age, term, margin, time, kimarite, start_mark, back_mark
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    item.get("term"),
                    item.get("margin"),
                    item.get("time"),
                    item.get("kimarite"),
                    item.get("start_mark"),
                    item.get("back_mark"),
                )
                for item in results
            ],
        )

        conn.executemany(
            """
            INSERT INTO payout
                (race_id, bet_type, combination, payout, popularity)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    race["race_id"],
                    item.get("bet_type"),
                    item.get("combination"),
                    item.get("payout"),
                    item.get("popularity"),
                )
                for item in payouts
            ],
        )

        conn.executemany(
            """
            INSERT INTO race_lineup
                (race_id, car_no, line_no, line_position)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    race["race_id"],
                    item.get("car_no"),
                    item.get("line_no"),
                    item.get("line_position"),
                )
                for item in race.get("lineup", [])
            ],
        )

        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise

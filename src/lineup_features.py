import argparse
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .db import connect, init_db


JST = timezone(timedelta(hours=9))
DEFAULT_KEEP_DAYS = 30


FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
SEPARATOR_TRANSLATION = str.maketrans({
    "／": "/",
    "｜": "/",
    "|": "/",
    "－": "-",
    "ー": "-",
    "―": "-",
    "–": "-",
    "−": "-",
    "　": " ",
})


def rows(conn, sql: str, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def normalize_lineup_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.translate(FULLWIDTH_DIGITS).translate(SEPARATOR_TRANSLATION)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *([/\n]) *", r"\1", text)
    text = re.sub(r" *- *", "-", text)
    return text.strip()


def parse_lineup_text(value: str | None) -> list[list[int]]:
    text = normalize_lineup_text(value)
    if not text:
        return []

    if "/" in text or "\n" in text:
        parts = [part for part in re.split(r"[/\n]+", text) if part.strip()]
    else:
        parts = [text]

    groups: list[list[int]] = []
    for part in parts:
        car_nos = [int(item) for item in re.findall(r"\d+", part) if 1 <= int(item) <= 9]
        if car_nos:
            groups.append(car_nos)
    return groups


def position_label(line_size: int, line_position: int) -> str:
    if line_size == 1:
        return "tanki"
    if line_position == 1:
        return "leader"
    if line_position == 2:
        return "second"
    if line_position == 3:
        return "third"
    return "fourth_plus"


def validate_groups(groups: list[list[int]], expected_car_nos: set[int]) -> tuple[bool, str]:
    if not groups:
        return False, "empty"
    flattened = [car_no for group in groups for car_no in group]
    if len(flattened) != len(set(flattened)):
        return False, "duplicate_car_no"
    if expected_car_nos and not expected_car_nos.issubset(set(flattened)):
        return False, "car_no_mismatch"
    return True, "ok"


def build_features_for_race(race: dict, results: list[dict]) -> tuple[list[dict], str]:
    expected_car_nos = {int(row["car_no"]) for row in results if row.get("car_no") is not None}
    result_by_car_no = {
        int(row["car_no"]): row
        for row in results
        if row.get("car_no") is not None
    }
    groups = parse_lineup_text(race.get("lineup_text"))
    is_valid, parse_status = validate_groups(groups, expected_car_nos)
    if not is_valid:
        return [], parse_status

    line_sizes = [len(group) for group in groups]
    starter_count = sum(line_sizes)
    line_count = len(groups)
    bunsen_count = sum(1 for size in line_sizes if size >= 2)
    tanki_count = sum(1 for size in line_sizes if size == 1)
    max_line_size = max(line_sizes) if line_sizes else 0
    now = datetime.now(JST).isoformat(timespec="seconds")

    features = []
    for line_no, group in enumerate(groups, start=1):
        line_size = len(group)
        for line_position, car_no in enumerate(group, start=1):
            result = result_by_car_no.get(car_no, {})
            followers = line_size - line_position
            features.append({
                "race_id": race["race_id"],
                "race_date": race["race_date"],
                "venue": race.get("venue"),
                "race_no": race.get("race_no"),
                "car_no": car_no,
                "racer_name": result.get("racer_name"),
                "prefecture": result.get("prefecture"),
                "term": result.get("term"),
                "rank": result.get("rank"),
                "line_no": line_no,
                "line_size": line_size,
                "line_position": line_position,
                "position_label": position_label(line_size, line_position),
                "followers": followers,
                "is_leader": 1 if line_size >= 2 and line_position == 1 else 0,
                "is_tanki": 1 if line_size == 1 else 0,
                "is_max_line": 1 if line_size == max_line_size else 0,
                "starter_count": starter_count,
                "line_count": line_count,
                "bunsen_count": bunsen_count,
                "tanki_count": tanki_count,
                "max_line_size": max_line_size,
                "parse_status": parse_status,
                "source_lineup_text": race.get("lineup_text"),
                "created_at": now,
            })
    return features, parse_status


def feature_values(feature: dict) -> tuple:
    return (
        feature["race_id"],
        feature["race_date"],
        feature["venue"],
        feature["race_no"],
        feature["car_no"],
        feature["racer_name"],
        feature["prefecture"],
        feature["term"],
        feature["rank"],
        feature["line_no"],
        feature["line_size"],
        feature["line_position"],
        feature["position_label"],
        feature["followers"],
        feature["is_leader"],
        feature["is_tanki"],
        feature["is_max_line"],
        feature["starter_count"],
        feature["line_count"],
        feature["bunsen_count"],
        feature["tanki_count"],
        feature["max_line_size"],
        feature["parse_status"],
        feature["source_lineup_text"],
        feature["created_at"],
    )


def condition_rows(feature: dict) -> list[tuple[str, str, dict]]:
    base = {
        "line_position": None,
        "position_label": None,
        "followers": None,
        "bunsen_count": None,
        "line_size": None,
        "is_tanki": None,
        "is_max_line": None,
    }
    conditions = []

    position = {**base, "line_position": feature["line_position"], "position_label": feature["position_label"]}
    conditions.append(("position", f"pos={feature['position_label']}", position))

    bunsen = {**base, "bunsen_count": feature["bunsen_count"]}
    conditions.append(("bunsen", f"bunsen={feature['bunsen_count']}", bunsen))

    line_size = {**base, "line_size": feature["line_size"]}
    conditions.append(("line_size", f"line_size={feature['line_size']}", line_size))

    if feature["is_tanki"]:
        tanki = {**base, "is_tanki": 1, "line_position": feature["line_position"], "position_label": "tanki"}
        conditions.append(("tanki", "tanki=1", tanki))
    elif feature["is_leader"]:
        followers = {
            **base,
            "line_position": feature["line_position"],
            "position_label": "leader",
            "followers": feature["followers"],
        }
        conditions.append(("leader_followers", f"leader_followers={feature['followers']}", followers))

    max_line = {**base, "is_max_line": feature["is_max_line"]}
    conditions.append(("max_line", f"is_max_line={feature['is_max_line']}", max_line))

    exact = {
        **base,
        "line_position": feature["line_position"],
        "position_label": feature["position_label"],
        "followers": feature["followers"],
        "bunsen_count": feature["bunsen_count"],
        "line_size": feature["line_size"],
        "is_tanki": feature["is_tanki"],
        "is_max_line": feature["is_max_line"],
    }
    conditions.append((
        "exact_condition",
        (
            f"pos={feature['position_label']}|followers={feature['followers']}|"
            f"bunsen={feature['bunsen_count']}|line_size={feature['line_size']}|"
            f"tanki={feature['is_tanki']}|max={feature['is_max_line']}"
        ),
        exact,
    ))

    return conditions


def build_stats(features: list[dict]) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    race_samples: dict[tuple, list[str]] = defaultdict(list)

    for feature in features:
        racer_name = feature.get("racer_name")
        rank = int(feature["rank"] or 0)
        if not racer_name or rank <= 0:
            continue
        for condition_type, condition_key, condition in condition_rows(feature):
            key = (
                racer_name,
                feature.get("prefecture"),
                feature.get("term"),
                condition_type,
                condition_key,
            )
            bucket = buckets.setdefault(key, {
                "racer_name": racer_name,
                "prefecture": feature.get("prefecture"),
                "term": feature.get("term"),
                "condition_type": condition_type,
                "condition_key": condition_key,
                **condition,
                "races": 0,
                "wins": 0,
                "seconds": 0,
                "thirds": 0,
                "top2": 0,
                "top3": 0,
                "min_race_date": feature["race_date"],
                "max_race_date": feature["race_date"],
            })
            bucket["races"] += 1
            bucket["wins"] += 1 if rank == 1 else 0
            bucket["seconds"] += 1 if rank == 2 else 0
            bucket["thirds"] += 1 if rank == 3 else 0
            bucket["top2"] += 1 if 1 <= rank <= 2 else 0
            bucket["top3"] += 1 if 1 <= rank <= 3 else 0
            bucket["min_race_date"] = min(bucket["min_race_date"], feature["race_date"])
            bucket["max_race_date"] = max(bucket["max_race_date"], feature["race_date"])
            if len(race_samples[key]) < 5 and feature["race_id"] not in race_samples[key]:
                race_samples[key].append(feature["race_id"])

    now = datetime.now(JST).isoformat(timespec="seconds")
    stats = []
    for key, bucket in buckets.items():
        races = bucket["races"]
        bucket["win_rate"] = round(bucket["wins"] / races * 100, 1) if races else 0
        bucket["top2_rate"] = round(bucket["top2"] / races * 100, 1) if races else 0
        bucket["top3_rate"] = round(bucket["top3"] / races * 100, 1) if races else 0
        bucket["sample_race_ids"] = ",".join(race_samples[key])
        bucket["updated_at"] = now
        stats.append(bucket)
    return stats


def stat_values(stat: dict) -> tuple:
    return (
        stat["racer_name"],
        stat.get("prefecture"),
        stat.get("term"),
        stat["condition_type"],
        stat["condition_key"],
        stat.get("line_position"),
        stat.get("position_label"),
        stat.get("followers"),
        stat.get("bunsen_count"),
        stat.get("line_size"),
        stat.get("is_tanki"),
        stat.get("is_max_line"),
        stat["races"],
        stat["wins"],
        stat["seconds"],
        stat["thirds"],
        stat["top2"],
        stat["top3"],
        stat["win_rate"],
        stat["top2_rate"],
        stat["top3_rate"],
        stat["min_race_date"],
        stat["max_race_date"],
        stat["sample_race_ids"],
        stat["updated_at"],
    )


def build_lineup_features(conn, keep_days: int = DEFAULT_KEEP_DAYS) -> dict:
    init_db(conn)
    races = rows(
        conn,
        """
        SELECT race_id, race_date, venue, race_no, lineup_text
        FROM race_master
        WHERE lineup_text IS NOT NULL AND lineup_text <> ''
        ORDER BY race_date, venue, race_no
        """,
    )
    results_by_race = defaultdict(list)
    for result in rows(conn, "SELECT * FROM race_result WHERE car_no IS NOT NULL"):
        results_by_race[result["race_id"]].append(result)

    all_features = []
    failed = 0
    failure_reasons = defaultdict(int)
    for race in races:
        features, status = build_features_for_race(race, results_by_race[race["race_id"]])
        if not features:
            failed += 1
            failure_reasons[status] += 1
            continue
        all_features.extend(features)

    cutoff_date = (datetime.now(JST).date() - timedelta(days=keep_days)).isoformat()
    recent_features = [
        feature
        for feature in all_features
        if feature.get("race_date") and feature["race_date"] >= cutoff_date
    ]
    stats = build_stats(all_features)

    conn.execute("DELETE FROM race_line_features")
    conn.executemany(
        """
        INSERT OR REPLACE INTO race_line_features
            (
                race_id, race_date, venue, race_no, car_no, racer_name,
                prefecture, term, rank, line_no, line_size, line_position,
                position_label, followers, is_leader, is_tanki, is_max_line,
                starter_count, line_count, bunsen_count, tanki_count,
                max_line_size, parse_status, source_lineup_text, created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [feature_values(feature) for feature in recent_features],
    )

    conn.execute("DELETE FROM racer_line_condition_stats")
    conn.executemany(
        """
        INSERT OR REPLACE INTO racer_line_condition_stats
            (
                racer_name, prefecture, term, condition_type, condition_key,
                line_position, position_label, followers, bunsen_count,
                line_size, is_tanki, is_max_line, races, wins, seconds,
                thirds, top2, top3, win_rate, top2_rate, top3_rate,
                min_race_date, max_race_date, sample_race_ids, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [stat_values(stat) for stat in stats],
    )
    conn.commit()

    return {
        "races": len(races),
        "parsed_races": len({feature["race_id"] for feature in all_features}),
        "failed_races": failed,
        "recent_features": len(recent_features),
        "stats": len(stats),
        "keep_days": keep_days,
        "failure_reasons": dict(failure_reasons),
    }


def run(keep_days: int = DEFAULT_KEEP_DAYS) -> dict:
    with connect() as conn:
        return build_lineup_features(conn, keep_days=keep_days)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build keirin line structure features")
    parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    args = parser.parse_args()
    print(run(keep_days=args.keep_days))


if __name__ == "__main__":
    main()

import argparse
from datetime import datetime, timedelta, timezone

from .db import connect, init_db


JST = timezone(timedelta(hours=9))
TRIFECTA = "3騾｣蜊・"
STAKE_AMOUNT = 100

PREDICTION_TYPES = [
    "本命予想",
    "穴予想",
    "ヘテオジマーベリック予想",
    "行動ヒヒーン予想",
    "感情ブヒー予想",
]


def default_target_date() -> str:
    return datetime.now(JST).date().isoformat()


def yesterday(value: str) -> str:
    return (datetime.fromisoformat(value).date() - timedelta(days=1)).isoformat()


def rows(conn, sql: str, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def scalar(conn, sql: str, params=()):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def racer_history(conn, entry: dict, venue: str | None) -> dict:
    if entry.get("prefecture") and entry.get("term"):
        where = "r.racer_name = ? AND r.prefecture = ? AND r.term = ?"
        params = [entry["racer_name"], entry["prefecture"], entry["term"]]
    elif entry.get("prefecture"):
        where = "r.racer_name = ? AND r.prefecture = ?"
        params = [entry["racer_name"], entry["prefecture"]]
    else:
        return {
            "starts": 0,
            "avg_rank": None,
            "win_rate": None,
            "top2_rate": None,
            "top3_rate": None,
            "venue_starts": 0,
            "venue_top3_rate": None,
            "upset_score": 0,
            "fade_score": 0,
            "activity_score": 0,
        }

    all_stats = conn.execute(
        f"""
        SELECT COUNT(*) AS starts,
               AVG(r.rank) AS avg_rank,
               AVG(CASE WHEN r.rank = 1 THEN 1.0 ELSE 0 END) * 100 AS win_rate,
               AVG(CASE WHEN r.rank <= 2 THEN 1.0 ELSE 0 END) * 100 AS top2_rate,
               AVG(CASE WHEN r.rank <= 3 THEN 1.0 ELSE 0 END) * 100 AS top3_rate
        FROM race_result r
        WHERE {where}
        """,
        params,
    ).fetchone()
    venue_stats = conn.execute(
        f"""
        SELECT COUNT(*) AS starts,
               AVG(CASE WHEN r.rank <= 3 THEN 1.0 ELSE 0 END) * 100 AS top3_rate
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE {where} AND m.venue = ?
        """,
        [*params, venue],
    ).fetchone()
    upset_score = scalar(
        conn,
        f"""
        SELECT COALESCE(AVG(p.popularity - r.rank), 0)
        FROM race_result r
        JOIN payout p ON p.race_id = r.race_id AND p.bet_type = ?
        WHERE {where} AND p.popularity IS NOT NULL AND r.rank <= 3
        """,
        [TRIFECTA, *params],
    ) or 0
    fade_score = scalar(
        conn,
        f"""
        SELECT COALESCE(AVG(r.rank - p.popularity), 0)
        FROM race_result r
        JOIN payout p ON p.race_id = r.race_id AND p.bet_type = ?
        WHERE {where} AND p.popularity IS NOT NULL
        """,
        [TRIFECTA, *params],
    ) or 0
    return {
        "starts": all_stats["starts"] or 0,
        "avg_rank": all_stats["avg_rank"],
        "win_rate": all_stats["win_rate"],
        "top2_rate": all_stats["top2_rate"],
        "top3_rate": all_stats["top3_rate"],
        "venue_starts": venue_stats["starts"] or 0,
        "venue_top3_rate": venue_stats["top3_rate"],
        "upset_score": upset_score,
        "fade_score": fade_score,
        "activity_score": all_stats["starts"] or 0,
    }


def car_context(conn, race: dict, car_no: int, target_date: str) -> dict:
    venue = race.get("venue")
    prior_date = yesterday(target_date)
    venue_win_rate = scalar(
        conn,
        """
        SELECT AVG(CASE WHEN r.rank = 1 THEN 1.0 ELSE 0 END) * 100
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE m.venue = ? AND r.car_no = ?
        """,
        (venue, car_no),
    )
    same_venue_yesterday = scalar(
        conn,
        "SELECT COUNT(*) FROM race_master WHERE venue = ? AND race_date = ?",
        (venue, prior_date),
    ) or 0
    yesterday_top3 = scalar(
        conn,
        """
        SELECT AVG(CASE WHEN r.rank <= 3 THEN 1.0 ELSE 0 END) * 100
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE m.venue = ? AND m.race_date = ? AND r.car_no = ?
        """,
        (venue, prior_date, car_no),
    )
    return {
        "venue_win_rate": venue_win_rate or 0,
        "same_venue_yesterday": bool(same_venue_yesterday),
        "yesterday_top3": yesterday_top3 or 0,
    }


def lineup_position(conn, race_id: str, car_no: int) -> int | None:
    return scalar(
        conn,
        """
        SELECT line_position
        FROM race_lineup_forecast
        WHERE race_id = ? AND car_no = ?
        LIMIT 1
        """,
        (race_id, car_no),
    )


def entry_scores(conn, race: dict, target_date: str) -> list[dict]:
    entries = rows(
        conn,
        """
        SELECT *
        FROM race_entry
        WHERE race_id = ?
        ORDER BY car_no
        """,
        (race["race_id"],),
    )
    scored = []
    for entry in entries:
        history = racer_history(conn, entry, race.get("venue"))
        context = car_context(conn, race, entry["car_no"], target_date)
        line_pos = lineup_position(conn, race["race_id"], entry["car_no"])
        line_bonus = 4 if line_pos == 1 else 2 if line_pos == 2 else 0
        score_value = (
            (entry.get("score") or 0)
            + (entry.get("win_rate") or history.get("win_rate") or 0) * 0.32
            + (entry.get("quinella_rate") or history.get("top2_rate") or 0) * 0.18
            + (entry.get("trifecta_rate") or history.get("top3_rate") or 0) * 0.12
            + (history.get("venue_top3_rate") or 0) * 0.08
            + context["venue_win_rate"] * 0.06
            + line_bonus
        )
        if context["same_venue_yesterday"]:
            score_value += context["yesterday_top3"] * 0.08
        scored.append({
            **entry,
            **history,
            **context,
            "line_position": line_pos,
            "base_score": round(score_value, 3),
        })
    return scored


def pick_combo(prediction_type: str, scored: list[dict]) -> tuple[list[int], float, str]:
    if len(scored) < 3:
        return [], 0, "出走表データが不足しています。"

    if prediction_type == "本命予想":
        ranked = sorted(scored, key=lambda row: row["base_score"], reverse=True)
        reason = "選手成績、会場傾向、車番傾向を総合して上位評価。"
    elif prediction_type == "穴予想":
        ranked = sorted(
            scored,
            key=lambda row: (row["base_score"] * 0.72 + (row.get("venue_top3_rate") or 0) * 0.2 - (row.get("win_rate") or 0) * 0.08),
            reverse=True,
        )
        reason = "本命寄りになりすぎないよう、会場相性と3着内の余地を重視。"
    elif prediction_type == "ヘテオジマーベリック予想":
        ranked = sorted(scored, key=lambda row: (row.get("upset_score") or 0, row["base_score"]), reverse=True)
        reason = "過去に人気を覆して上位に来た傾向を重視。"
    elif prediction_type == "行動ヒヒーン予想":
        ranked = sorted(scored, key=lambda row: (row.get("activity_score") or 0, -1 * (row.get("avg_rank") or 99), row["base_score"]), reverse=True)
        reason = "出走数と継続性、安定した平均着順を重視。"
    else:
        ranked = sorted(scored, key=lambda row: (row["base_score"] - max(row.get("fade_score") or 0, 0) * 2), reverse=True)
        reason = "人気倒れ傾向を避け、統計上の安定候補を残す。"

    combo = [int(row["car_no"]) for row in ranked[:3]]
    score_value = sum(float(row["base_score"]) for row in ranked[:3])
    if not any(row.get("same_venue_yesterday") for row in scored):
        reason += " 前日同会場データなしのため、累積会場傾向と選手成績を優先。"
    else:
        reason += " 前日同会場データがあるため、直近の会場傾向を補正。"
    return combo, round(score_value, 3), reason


def confidence(score_value: float, has_same_venue_yesterday: bool) -> str:
    if score_value >= 300 and has_same_venue_yesterday:
        return "A"
    if score_value >= 220:
        return "B"
    return "C"


def clear_date_predictions(conn, target_date: str) -> None:
    prediction_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM race_prediction WHERE race_date = ?",
            (target_date,),
        ).fetchall()
    ]
    if prediction_ids:
        conn.executemany("DELETE FROM race_prediction_result WHERE prediction_id = ?", [(item,) for item in prediction_ids])
    conn.execute("DELETE FROM race_prediction WHERE race_date = ?", (target_date,))


def generate_predictions(conn, target_date: str) -> int:
    races = rows(
        conn,
        """
        SELECT *
        FROM race_schedule
        WHERE race_date = ?
        ORDER BY venue, race_no
        """,
        (target_date,),
    )
    clear_date_predictions(conn, target_date)
    saved = 0
    for prediction_type in PREDICTION_TYPES:
        candidates = []
        for race in races:
            scored = entry_scores(conn, race, target_date)
            combo, score_value, reason = pick_combo(prediction_type, scored)
            if len(combo) != 3:
                continue
            has_same_venue_yesterday = any(row.get("same_venue_yesterday") for row in scored)
            candidates.append({
                "race": race,
                "combo": combo,
                "score": score_value,
                "confidence": confidence(score_value, has_same_venue_yesterday),
                "reason": reason,
            })
        candidates.sort(key=lambda row: row["score"], reverse=True)
        for candidate in candidates[:3]:
            race = candidate["race"]
            combo = candidate["combo"]
            conn.execute(
                """
                INSERT INTO race_prediction
                    (
                        race_id, race_date, prediction_type, predicted_1st,
                        predicted_2nd, predicted_3rd, confidence, score,
                        reason_text, stake_amount, created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    race["race_id"],
                    target_date,
                    prediction_type,
                    combo[0],
                    combo[1],
                    combo[2],
                    candidate["confidence"],
                    candidate["score"],
                    candidate["reason"],
                    STAKE_AMOUNT,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            saved += 1
    conn.commit()
    return saved


def evaluate_predictions(conn) -> int:
    predictions = rows(
        conn,
        """
        SELECT p.*
        FROM race_prediction p
        JOIN race_master m ON m.race_id = p.race_id
        LEFT JOIN race_prediction_result pr ON pr.prediction_id = p.id
        WHERE pr.id IS NULL
        """,
    )
    checked = 0
    for prediction in predictions:
        actual_rows = rows(
            conn,
            """
            SELECT rank, car_no
            FROM race_result
            WHERE race_id = ? AND rank IN (1, 2, 3)
            ORDER BY rank
            """,
            (prediction["race_id"],),
        )
        if len(actual_rows) < 3:
            continue
        actual = [int(row["car_no"]) for row in actual_rows]
        predicted = [int(prediction["predicted_1st"]), int(prediction["predicted_2nd"]), int(prediction["predicted_3rd"])]
        exact = predicted == actual
        payout = scalar(
            conn,
            """
            SELECT payout
            FROM payout
            WHERE race_id = ? AND bet_type = ? AND combination = ?
            LIMIT 1
            """,
            (prediction["race_id"], TRIFECTA, "-".join(str(item) for item in actual)),
        )
        if payout is None:
            payout = scalar(
                conn,
                "SELECT payout FROM payout WHERE race_id = ? AND bet_type = ? LIMIT 1",
                (prediction["race_id"], TRIFECTA),
            )
        return_amount = int(payout or 0) if exact else 0
        stake = int(prediction["stake_amount"] or STAKE_AMOUNT)
        roi = (return_amount / stake * 100) if stake else 0
        conn.execute(
            """
            INSERT OR REPLACE INTO race_prediction_result
                (
                    prediction_id, race_id, actual_1st, actual_2nd, actual_3rd,
                    hit_exact, hit_1st, hit_top2, hit_top3_count, payout,
                    stake_amount, return_amount, roi, checked_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction["id"],
                prediction["race_id"],
                actual[0],
                actual[1],
                actual[2],
                1 if exact else 0,
                1 if predicted[0] == actual[0] else 0,
                1 if set(predicted[:2]) == set(actual[:2]) else 0,
                len(set(predicted) & set(actual)),
                payout,
                stake,
                return_amount,
                roi,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        checked += 1
    conn.commit()
    return checked


def run(target_date: str | None = None) -> dict:
    target_date = target_date or default_target_date()
    with connect() as conn:
        init_db(conn)
        checked = evaluate_predictions(conn)
        saved = generate_predictions(conn, target_date)
    return {"date": target_date, "predictions": saved, "checked": checked}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and evaluate keirin predictions")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD. Default: today")
    args = parser.parse_args()
    result = run(args.date)
    print(result)


if __name__ == "__main__":
    main()

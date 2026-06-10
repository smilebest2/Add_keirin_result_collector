import argparse
import html
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, ROOT_DIR
from .db import connect, init_db


DOCS_DIR = ROOT_DIR / "docs"


def h(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def yen(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        if value.endswith("円"):
            return value
        value = re.sub(r"[^\d-]", "", value)
        if not value:
            return ""
    return f"{int(value):,}円"


def pct(value) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%"


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rows(conn, sql: str, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def scalar(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchone()[0]


def page(title: str, active: str, body: str) -> str:
    nav_items = [
        ("index.html", "TOP", "top"),
        ("venues.html", "会場分析", "venues"),
        ("car_numbers.html", "車番分析", "cars"),
        ("payouts.html", "配当分析", "payouts"),
        ("racers.html", "選手分析", "racers"),
        ("custom.html", "独自ランキング", "custom"),
    ]
    nav = "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in nav_items
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)} | 競輪統計</title>
  <style>
    :root {{
      --bg: #f5f7f9;
      --panel: #ffffff;
      --ink: #20242a;
      --muted: #697586;
      --line: #dbe1e8;
      --accent: #0f766e;
      --accent-soft: #e0f2ef;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px 20px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    nav a {{
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--ink);
      padding: 7px 10px;
      text-decoration: none;
      font-size: 14px;
      background: #fbfcfd;
    }}
    nav a.active {{
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 700;
    }}
    main .wrap {{
      display: grid;
      gap: 16px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 12px;
    }}
    .card, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .card {{
      padding: 14px;
    }}
    .card span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .card strong {{
      display: block;
      margin-top: 3px;
      font-size: 22px;
    }}
    section h2 {{
      margin: 0;
      padding: 13px 15px;
      border-bottom: 1px solid var(--line);
      font-size: 17px;
      background: #fafbfc;
      letter-spacing: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      background: #fbfcfd;
      font-weight: 700;
    }}
    .empty {{
      padding: 22px;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 780px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
      section {{ overflow-x: auto; }}
      table {{ min-width: 720px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>{h(title)}</h1>
      <nav>{nav}</nav>
    </div>
  </header>
  <main>
    <div class="wrap">
      {body}
    </div>
  </main>
</body>
</html>
"""


def table(headers: list[str], data: list[dict], fields: list[str], empty="データがありません") -> str:
    if not data:
        return f'<div class="empty">{h(empty)}</div>'
    header_html = "".join(f"<th>{h(header)}</th>" for header in headers)
    body_html = ""
    for row in data:
        body_html += "<tr>" + "".join(f"<td>{h(row.get(field))}</td>" for field in fields) + "</tr>"
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def section(title: str, html_body: str) -> str:
    return f"<section><h2>{h(title)}</h2>{html_body}</section>"


def summary(conn):
    return {
        "races": scalar(conn, "SELECT COUNT(*) FROM race_master"),
        "racers": scalar(conn, "SELECT COUNT(DISTINCT racer_name) FROM race_result"),
        "payout_total": scalar(conn, "SELECT COALESCE(SUM(payout), 0) FROM payout"),
        "latest": scalar(conn, "SELECT MAX(created_at) FROM race_master"),
    }


def render_top(conn) -> str:
    s = summary(conn)
    body = f"""
    <div class="grid">
      <div class="card"><span>総レース数</span><strong>{h(s["races"])}</strong></div>
      <div class="card"><span>総選手数</span><strong>{h(s["racers"])}</strong></div>
      <div class="card"><span>総配当額</span><strong>{h(yen(s["payout_total"]))}</strong></div>
      <div class="card"><span>最新更新日</span><strong>{h(s["latest"] or "-")}</strong></div>
    </div>
    """
    body += section("最近のレース", table(
        ["日付", "会場", "R", "レース名", "発走", "天候", "風速", "並び"],
        rows(conn, """
            SELECT race_date, venue, race_no, race_title, start_time, weather,
                   CASE WHEN wind_speed IS NULL THEN '' ELSE wind_speed || 'm/s' END AS wind_speed,
                   lineup_text
            FROM race_master
            ORDER BY race_date DESC, venue, race_no
            LIMIT 50
        """),
        ["race_date", "venue", "race_no", "race_title", "start_time", "weather", "wind_speed", "lineup_text"],
    ))
    return page("競輪統計 TOP", "top", body)


def render_venues(conn) -> str:
    avg_times = rows(conn, """
        SELECT m.venue, ROUND(AVG(CAST(r.time AS REAL)), 2) AS avg_time,
               COUNT(*) AS samples
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE r.time IS NOT NULL AND r.time != ''
        GROUP BY m.venue
        ORDER BY avg_time ASC
    """)
    trifecta = rows(conn, """
        SELECT m.venue,
               ROUND(AVG(p.payout), 0) AS avg_payout,
               COUNT(*) AS races,
               ROUND(AVG(CASE WHEN p.payout >= 10000 THEN 100.0 ELSE 0 END), 1) AS high_rate
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = '3連単'
        GROUP BY m.venue
        ORDER BY avg_payout DESC
    """)
    medians = median_by_group(conn, "m.venue", "p.payout", """
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = '3連単'
    """)
    turbulence = []
    for row in trifecta:
        median = medians.get(row["venue"])
        score = (row["avg_payout"] or 0) + (median or 0) + ((row["high_rate"] or 0) * 100)
        turbulence.append({
            "venue": row["venue"],
            "avg_payout": yen(row["avg_payout"]),
            "median": yen(median),
            "high_rate": pct(row["high_rate"]),
            "score": f"{score:.0f}",
        })
    turbulence.sort(key=lambda item: float(item["score"]), reverse=True)

    car_tendency = rows(conn, """
        SELECT m.venue, r.car_no,
               COUNT(*) AS starts,
               SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) AS wins,
               ROUND(SUM(CASE WHEN r.rank = 1 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS win_rate
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        GROUP BY m.venue, r.car_no
        ORDER BY m.venue, r.car_no
    """)
    for row in trifecta:
        row["avg_payout"] = yen(row["avg_payout"])
        row["high_rate"] = pct(row["high_rate"])
    body = section("会場別平均タイム", table(
        ["会場", "平均タイム", "サンプル"],
        avg_times,
        ["venue", "avg_time", "samples"],
    ))
    body += section("会場別 3連単平均配当・高配当率", table(
        ["会場", "平均配当", "対象数", "10000円以上割合"],
        trifecta,
        ["venue", "avg_payout", "races", "high_rate"],
    ))
    body += section("会場別荒れ度ランキング", table(
        ["会場", "平均配当", "中央値", "高配当率", "指数"],
        turbulence,
        ["venue", "avg_payout", "median", "high_rate", "score"],
    ))
    body += section("会場別車番傾向", table(
        ["会場", "車番", "出走", "1着", "勝率"],
        car_tendency,
        ["venue", "car_no", "starts", "wins", "win_rate"],
    ))
    return page("会場分析", "venues", body)


def render_car_numbers(conn) -> str:
    stats = rows(conn, """
        SELECT car_no,
               COUNT(*) AS starts,
               SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rank <= 2 THEN 1 ELSE 0 END) AS quinella,
               SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) AS top3,
               ROUND(SUM(CASE WHEN rank = 1 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS win_rate,
               ROUND(SUM(CASE WHEN rank <= 2 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS quinella_rate,
               ROUND(SUM(CASE WHEN rank <= 3 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM race_result
        GROUP BY car_no
        ORDER BY wins DESC, win_rate DESC
    """)
    recovery = car_recovery(conn)
    body = section("1着車番ランキング・車番別勝率", table(
        ["車番", "出走", "1着", "連対", "3着内", "勝率", "連対率", "3着内率"],
        stats,
        ["car_no", "starts", "wins", "quinella", "top3", "win_rate", "quinella_rate", "top3_rate"],
    ))
    body += section("車番別回収率 100円購入想定", table(
        ["車番", "対象レース", "払戻合計", "投資額", "回収率"],
        recovery,
        ["car_no", "races", "return_total", "investment", "recovery_rate"],
    ))
    return page("車番分析", "cars", body)


def render_payouts(conn) -> str:
    high = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, p.bet_type, p.combination,
               p.payout, p.popularity
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        ORDER BY p.payout DESC
        LIMIT 100
    """)
    tickets = [row.copy() for row in high if row["payout"] and row["payout"] >= 10000]
    monthly = rows(conn, """
        SELECT CAST(strftime('%m', race_date) AS INTEGER) AS month,
               ROUND(AVG(p.payout), 0) AS avg_payout
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = '3連単'
        GROUP BY month
        ORDER BY month
    """)
    weekday = rows(conn, """
        SELECT CASE strftime('%w', race_date)
                 WHEN '0' THEN '日'
                 WHEN '1' THEN '月'
                 WHEN '2' THEN '火'
                 WHEN '3' THEN '水'
                 WHEN '4' THEN '木'
                 WHEN '5' THEN '金'
                 ELSE '土'
               END AS weekday,
               ROUND(AVG(p.payout), 0) AS avg_payout
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = '3連単'
        GROUP BY strftime('%w', race_date)
        ORDER BY strftime('%w', race_date)
    """)
    medians = [{"bet_type": key, "median": yen(value)} for key, value in median_by_group(
        conn,
        "p.bet_type",
        "p.payout",
        "FROM payout p",
    ).items()]
    for collection in (high, tickets, monthly, weekday):
        for row in collection:
            if "payout" in row:
                row["payout"] = yen(row["payout"])
            if "avg_payout" in row:
                row["avg_payout"] = yen(row["avg_payout"])
    body = section("高配当ランキング TOP100", table(
        ["日付", "会場", "R", "賭式", "組番", "払戻", "人気"],
        high,
        ["race_date", "venue", "race_no", "bet_type", "combination", "payout", "popularity"],
    ))
    body += section("万車券ランキング", table(
        ["日付", "会場", "R", "賭式", "組番", "払戻", "人気"],
        tickets,
        ["race_date", "venue", "race_no", "bet_type", "combination", "payout", "popularity"],
    ))
    body += section("配当中央値ランキング", table(["賭式", "中央値"], medians, ["bet_type", "median"]))
    body += section("月別 3連単平均配当", table(["月", "平均配当"], monthly, ["month", "avg_payout"]))
    body += section("曜日別 3連単平均配当", table(["曜日", "平均配当"], weekday, ["weekday", "avg_payout"]))
    return page("配当分析", "payouts", body)


def render_racers(conn) -> str:
    base = """
        SELECT racer_name,
               COUNT(*) AS starts,
               SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rank <= 2 THEN 1 ELSE 0 END) AS quinella,
               SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) AS top3,
               ROUND(AVG(rank), 2) AS avg_rank,
               ROUND(SUM(CASE WHEN rank = 1 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS win_rate,
               ROUND(SUM(CASE WHEN rank <= 2 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS quinella_rate,
               ROUND(SUM(CASE WHEN rank <= 3 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM race_result
        GROUP BY racer_name
    """
    starts = rows(conn, base + " ORDER BY starts DESC, racer_name LIMIT 100")
    wins = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= 30 ORDER BY win_rate DESC, starts DESC LIMIT 100")
    quinella = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= 30 ORDER BY quinella_rate DESC, starts DESC LIMIT 100")
    top3 = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= 30 ORDER BY top3_rate DESC, starts DESC LIMIT 100")
    avg_rank = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= 30 ORDER BY avg_rank ASC, starts DESC LIMIT 100")
    kimarite = rows(conn, """
        SELECT racer_name, kimarite, COUNT(*) AS count
        FROM race_result
        WHERE rank = 1 AND kimarite IS NOT NULL AND kimarite != ''
        GROUP BY racer_name, kimarite
        ORDER BY count DESC
        LIMIT 100
    """)
    body = section("選手別出走数ランキング", table(
        ["選手", "出走", "1着", "連対", "3着内", "平均着順"],
        starts,
        ["racer_name", "starts", "wins", "quinella", "top3", "avg_rank"],
    ))
    body += section("選手別勝率ランキング 出走30回以上", table(
        ["選手", "出走", "勝率", "1着", "平均着順"],
        wins,
        ["racer_name", "starts", "win_rate", "wins", "avg_rank"],
    ))
    body += section("選手別連対率ランキング 出走30回以上", table(
        ["選手", "出走", "連対率", "連対", "平均着順"],
        quinella,
        ["racer_name", "starts", "quinella_rate", "quinella", "avg_rank"],
    ))
    body += section("選手別3着内率ランキング 出走30回以上", table(
        ["選手", "出走", "3着内率", "3着内", "平均着順"],
        top3,
        ["racer_name", "starts", "top3_rate", "top3", "avg_rank"],
    ))
    body += section("選手別平均着順 出走30回以上", table(
        ["選手", "出走", "平均着順", "勝率", "3着内率"],
        avg_rank,
        ["racer_name", "starts", "avg_rank", "win_rate", "top3_rate"],
    ))
    body += section("選手別決まり手ランキング", table(
        ["選手", "決まり手", "回数"],
        kimarite,
        ["racer_name", "kimarite", "count"],
    ))
    return page("選手分析", "racers", body)


def render_custom(conn) -> str:
    # Popularity is payout popularity, not individual racer popularity. These are proxy indices.
    upset = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, r.racer_name, r.rank,
               p.popularity, (p.popularity - r.rank) AS score
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        JOIN payout p ON p.race_id = r.race_id AND p.bet_type = '3連単'
        WHERE p.popularity IS NOT NULL AND r.rank <= 3
        ORDER BY score DESC
        LIMIT 100
    """)
    fade = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, r.racer_name, r.rank,
               p.popularity, (r.rank - p.popularity) AS score
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        JOIN payout p ON p.race_id = r.race_id AND p.bet_type = '3連単'
        WHERE p.popularity IS NOT NULL
        ORDER BY score DESC
        LIMIT 100
    """)
    growth = growth_index(conn)
    yearly = rows(conn, """
        SELECT racer_name, strftime('%Y', m.race_date) AS year, COUNT(*) AS starts
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        GROUP BY racer_name, year
        ORDER BY starts DESC
        LIMIT 100
    """)
    body = section("ヘテオジマーベリック指数", table(
        ["日付", "会場", "R", "選手", "着順", "人気", "指数"],
        upset,
        ["race_date", "venue", "race_no", "racer_name", "rank", "popularity", "score"],
    ))
    body += section("感情ブヒー指数", table(
        ["日付", "会場", "R", "選手", "着順", "人気", "指数"],
        fade,
        ["race_date", "venue", "race_no", "racer_name", "rank", "popularity", "score"],
    ))
    body += section("達成パオーン指数", table(
        ["選手", "直近20走", "過去20走", "指数"],
        growth,
        ["racer_name", "recent_avg", "past_avg", "score"],
    ))
    body += section("行動ヒヒーン指数", table(
        ["選手", "年", "出走数"],
        yearly,
        ["racer_name", "year", "starts"],
    ))
    return page("独自ランキング", "custom", body)


def median_by_group(conn, group_expr: str, value_expr: str, from_sql: str) -> dict:
    data = defaultdict(list)
    for row in conn.execute(f"SELECT {group_expr} AS group_key, {value_expr} AS value {from_sql}"):
        value = to_float(row["value"])
        if row["group_key"] is not None and value is not None:
            data[row["group_key"]].append(value)
    return {key: statistics.median(values) for key, values in data.items() if values}


def car_recovery(conn) -> list[dict]:
    race_count = scalar(conn, "SELECT COUNT(*) FROM race_master")
    returns = defaultdict(int)
    for row in conn.execute("""
        SELECT p.combination, p.payout
        FROM payout p
        WHERE p.bet_type = '2車単'
    """):
        first_car = str(row["combination"]).split("-")[0]
        if first_car.isdigit():
            returns[int(first_car)] += int(row["payout"] or 0)
    output = []
    for car_no in range(1, 10):
        investment = race_count * 100
        recovery_rate = (returns[car_no] / investment * 100) if investment else 0
        output.append({
            "car_no": car_no,
            "races": race_count,
            "return_total": yen(returns[car_no]),
            "investment": yen(investment),
            "recovery_rate": pct(recovery_rate),
        })
    return output


def growth_index(conn) -> list[dict]:
    by_racer = defaultdict(list)
    for row in conn.execute("""
        SELECT r.racer_name, r.rank
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        ORDER BY r.racer_name, m.race_date, m.race_no
    """):
        by_racer[row["racer_name"]].append(row["rank"])
    rankings = []
    for racer_name, ranks in by_racer.items():
        if len(ranks) < 40:
            continue
        recent = ranks[-20:]
        past = ranks[-40:-20]
        recent_avg = statistics.mean(recent)
        past_avg = statistics.mean(past)
        score = past_avg - recent_avg
        rankings.append({
            "racer_name": racer_name,
            "recent_avg": f"{recent_avg:.2f}",
            "past_avg": f"{past_avg:.2f}",
            "score": f"{score:.2f}",
        })
    rankings.sort(key=lambda row: float(row["score"]), reverse=True)
    return rankings[:100]


def export_all(output_dir: Path = DOCS_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with connect(DB_PATH) as conn:
        init_db(conn)
        pages = {
            "index.html": render_top(conn),
            "venues.html": render_venues(conn),
            "car_numbers.html": render_car_numbers(conn),
            "payouts.html": render_payouts(conn),
            "racers.html": render_racers(conn),
            "custom.html": render_custom(conn),
        }
    written = []
    for filename, content in pages.items():
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    (output_dir / ".nojekyll").touch()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate keirin analytics HTML reports")
    parser.parse_args()
    for path in export_all():
        print(f"Exported {path}")


if __name__ == "__main__":
    main()

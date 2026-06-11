import argparse
import html
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, LOG_DIR, ROOT_DIR
from .db import connect, init_db


DOCS_DIR = ROOT_DIR / "docs"
TRIFECTA = "3連単"


def h(value) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"winticket", "", text, flags=re.IGNORECASE)
    text = text.replace("ウィンチケット", "")
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = text.replace("・杯", "杯")
    return html.escape(text, quote=True)


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
    return f"{float(value):.1f}%"


def number(value) -> str:
    if value is None:
        return ""
    return f"{int(value):,}"


def decimal(value, digits=2) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rows(conn, sql: str, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def scalar(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchone()[0]


def table(headers: list[str], data: list[dict], fields: list[str], empty="データがありません") -> str:
    if not data:
        return f'<div class="empty">{h(empty)}</div>'
    header_html = "".join(f"<th>{h(header)}</th>" for header in headers)
    body_html = ""
    for row in data:
        body_html += "<tr>" + "".join(f"<td>{h(row.get(field))}</td>" for field in fields) + "</tr>"
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def section(title: str, html_body: str, intro: str = "") -> str:
    lead = f'<p class="section-lead">{h(intro)}</p>' if intro else ""
    return f"<section><h2>{h(title)}</h2>{lead}{html_body}</section>"


def page(title: str, active: str, body: str) -> str:
    nav_items = [
        ("index.html", "TOP", "top"),
        ("venues.html", "会場分析", "venues"),
        ("car_numbers.html", "車番分析", "cars"),
        ("payouts.html", "配当分析", "payouts"),
        ("racers.html", "選手分析", "racers"),
        ("races.html", "レース一覧", "races"),
        ("quality.html", "データ品質", "quality"),
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
      --accent-2: #1d4ed8;
      --accent-3: #b45309;
      --soft: #e0f2ef;
      --soft-2: #e8eefc;
      --warn: #fef3c7;
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
      max-width: 1240px;
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
      background: var(--soft);
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
    .grid.two {{
      grid-template-columns: repeat(2, minmax(240px, 1fr));
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
    .section-lead {{
      margin: 12px 15px 0;
      color: var(--muted);
      font-size: 13px;
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
      white-space: nowrap;
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
    .chart {{
      display: grid;
      gap: 9px;
      padding: 14px 15px 16px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(92px, 170px) minmax(160px, 1fr) 92px;
      gap: 10px;
      align-items: center;
      font-size: 13px;
    }}
    .bar-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bar-track {{
      height: 12px;
      border-radius: 999px;
      background: #eef2f6;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      min-width: 2px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }}
    .bar-value {{
      color: var(--muted);
      text-align: right;
      white-space: nowrap;
    }}
    .heatmap {{
      padding: 0 0 2px;
      overflow-x: auto;
    }}
    .heatmap td {{
      min-width: 58px;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .heat-0 {{ background: #f8fafc; }}
    .heat-1 {{ background: #e8f4f1; }}
    .heat-2 {{ background: #cbe9e2; }}
    .heat-3 {{ background: #94d6c8; }}
    .heat-4 {{ background: #4eb7a2; color: #062f29; font-weight: 700; }}
    .note {{
      padding: 12px 15px;
      color: var(--muted);
      background: #fbfcfd;
      border-top: 1px solid var(--line);
      font-size: 13px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 14px 15px 16px;
    }}
    .action-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      border-radius: 8px;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #ffffff;
      padding: 8px 12px;
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
    }}
    .action-button.secondary {{
      border-color: #b91c1c;
      background: #b91c1c;
    }}
    @media (max-width: 780px) {{
      .grid, .grid.two {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
      section {{ overflow-x: auto; }}
      table {{ min-width: 760px; }}
      .bar-row {{ grid-template-columns: 96px minmax(130px, 1fr) 74px; }}
      h1 {{ font-size: 24px; }}
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


def bar_chart(data: list[dict], label_field: str, value_field: str, value_format=str, limit=12) -> str:
    values = [to_float(row.get(value_field)) for row in data[:limit]]
    values = [value for value in values if value is not None]
    if not data or not values:
        return '<div class="empty">グラフ化できるデータがありません</div>'
    max_value = max(values) or 1
    html_rows = []
    for row in data[:limit]:
        value = to_float(row.get(value_field))
        if value is None:
            continue
        width = max(1, min(100, value / max_value * 100))
        html_rows.append(
            '<div class="bar-row">'
            f'<div class="bar-label" title="{h(row.get(label_field))}">{h(row.get(label_field))}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value">{h(value_format(value))}</div>'
            '</div>'
        )
    return '<div class="chart">' + "".join(html_rows) + "</div>"


def heat_class(value, max_value) -> str:
    if value is None or max_value <= 0:
        return "heat-0"
    ratio = value / max_value
    if ratio >= 0.8:
        return "heat-4"
    if ratio >= 0.55:
        return "heat-3"
    if ratio >= 0.3:
        return "heat-2"
    if ratio > 0:
        return "heat-1"
    return "heat-0"


def venue_car_heatmap(conn) -> str:
    data = rows(conn, """
        SELECT m.venue, r.car_no,
               COUNT(*) AS starts,
               ROUND(SUM(CASE WHEN r.rank = 1 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS win_rate
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE r.car_no IS NOT NULL
        GROUP BY m.venue, r.car_no
    """)
    if not data:
        return '<div class="empty">データがありません</div>'
    venues = sorted({row["venue"] for row in data})
    rates = {(row["venue"], row["car_no"]): row["win_rate"] for row in data}
    starts = {(row["venue"], row["car_no"]): row["starts"] for row in data}
    max_rate = max((row["win_rate"] or 0 for row in data), default=0)
    header = "<tr><th>会場</th>" + "".join(f"<th>{car}番</th>" for car in range(1, 10)) + "</tr>"
    body = ""
    for venue in venues:
        body += f"<tr><th>{h(venue)}</th>"
        for car in range(1, 10):
            rate = rates.get((venue, car))
            sample = starts.get((venue, car), 0)
            text = "" if rate is None else f"{rate:.1f}%"
            body += f'<td class="{heat_class(rate, max_rate)}" title="出走 {sample}">{h(text)}</td>'
        body += "</tr>"
    return f'<div class="heatmap"><table><thead>{header}</thead><tbody>{body}</tbody></table></div>'


def median_by_group(conn, group_expr: str, value_expr: str, from_sql: str, params=()) -> dict:
    data = defaultdict(list)
    for row in conn.execute(f"SELECT {group_expr} AS group_key, {value_expr} AS value {from_sql}", params):
        value = to_float(row["value"])
        if row["group_key"] is not None and value is not None:
            data[row["group_key"]].append(value)
    return {key: statistics.median(values) for key, values in data.items() if values}


def summary(conn):
    return {
        "races": scalar(conn, "SELECT COUNT(*) FROM race_master"),
        "racers": scalar(conn, "SELECT COUNT(DISTINCT racer_name) FROM race_result"),
        "venues": scalar(conn, "SELECT COUNT(DISTINCT venue) FROM race_master"),
        "payout_total": scalar(conn, "SELECT COALESCE(SUM(payout), 0) FROM payout"),
        "latest_created": scalar(conn, "SELECT MAX(created_at) FROM race_master"),
        "latest_race_date": scalar(conn, "SELECT MAX(race_date) FROM race_master"),
        "first_race_date": scalar(conn, "SELECT MIN(race_date) FROM race_master"),
        "trifecta_avg": scalar(conn, "SELECT ROUND(AVG(payout), 0) FROM payout WHERE bet_type = ?", (TRIFECTA,)),
        "trifecta_max": scalar(conn, "SELECT MAX(payout) FROM payout WHERE bet_type = ?", (TRIFECTA,)),
        "trifecta_high_rate": scalar(
            conn,
            "SELECT ROUND(AVG(CASE WHEN payout >= 10000 THEN 100.0 ELSE 0 END), 1) FROM payout WHERE bet_type = ?",
            (TRIFECTA,),
        ),
    }


def render_top(conn) -> str:
    s = summary(conn)
    daily = rows(conn, """
        SELECT race_date, COUNT(*) AS races
        FROM race_master
        GROUP BY race_date
        ORDER BY race_date DESC
        LIMIT 30
    """)
    daily_chart = list(reversed(daily))
    monthly = rows(conn, """
        SELECT strftime('%Y-%m', m.race_date) AS month,
               ROUND(AVG(p.payout), 0) AS avg_payout
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = ?
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """, (TRIFECTA,))
    recent = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, m.race_title, m.start_time,
               m.weather,
               CASE WHEN m.wind_speed IS NULL THEN '' ELSE m.wind_speed || 'm/s' END AS wind_speed,
               (
                 SELECT r.car_no
                 FROM race_result r
                 WHERE r.race_id = m.race_id AND r.rank = 1
                 ORDER BY r.id
                 LIMIT 1
               ) AS winner_car,
               (
                 SELECT r.racer_name
                 FROM race_result r
                 WHERE r.race_id = m.race_id AND r.rank = 1
                 ORDER BY r.id
                 LIMIT 1
               ) AS winner,
               p.payout AS trifecta_payout
        FROM race_master m
        LEFT JOIN payout p ON p.race_id = m.race_id AND p.bet_type = ?
        ORDER BY m.race_date DESC, m.venue, m.race_no
        LIMIT 60
    """, (TRIFECTA,))
    for row in recent:
        row["trifecta_payout"] = yen(row["trifecta_payout"])

    body = f"""
    <div class="grid">
      <div class="card"><span>総レース数</span><strong>{h(number(s["races"]))}</strong></div>
      <div class="card"><span>総選手数</span><strong>{h(number(s["racers"]))}</strong></div>
      <div class="card"><span>総会場数</span><strong>{h(number(s["venues"]))}</strong></div>
      <div class="card"><span>最新レース日</span><strong>{h(s["latest_race_date"] or "-")}</strong></div>
      <div class="card"><span>3連単平均配当</span><strong>{h(yen(s["trifecta_avg"]))}</strong></div>
      <div class="card"><span>3連単万車券率</span><strong>{h(pct(s["trifecta_high_rate"]))}</strong></div>
      <div class="card"><span>3連単最高配当</span><strong>{h(yen(s["trifecta_max"]))}</strong></div>
      <div class="card"><span>最終保存日時</span><strong>{h(s["latest_created"] or "-")}</strong></div>
    </div>
    """
    body += section("運用操作", """
      <div class="actions">
        <a class="action-button" href="https://github.com/smilebest2/Add_keirin_result_collector/actions/workflows/collect.yml">手動で取得する</a>
        <a class="action-button secondary" href="https://github.com/smilebest2/Add_keirin_result_collector/actions/workflows/reset-data.yml">取得データを削除する</a>
      </div>
    """, "ボタン先のGitHub Actions画面で Run workflow を押すと実行できます。通常の自動取得は毎日8:00 JSTに前日分を取得します。")
    body += '<div class="grid two">'
    body += section("日別取得レース数", bar_chart(daily_chart, "race_date", "races", lambda v: f"{int(v)}R", 30))
    body += section("月別3連単平均配当", bar_chart(list(reversed(monthly)), "month", "avg_payout", yen, 12))
    body += "</div>"
    body += section("最新レース一覧", table(
        ["日付", "会場", "R", "レース名", "発走", "天候", "風速", "1着車番", "1着選手", "3連単"],
        recent,
        ["race_date", "venue", "race_no", "race_title", "start_time", "weather", "wind_speed", "winner_car", "winner", "trifecta_payout"],
    ))
    return page("競輪統計 TOP", "top", body)


def render_venues(conn) -> str:
    venue_stats = rows(conn, """
        WITH race_counts AS (
            SELECT venue, COUNT(*) AS races
            FROM race_master
            GROUP BY venue
        ),
        time_stats AS (
            SELECT m.venue, ROUND(AVG(CAST(NULLIF(r.time, '') AS REAL)), 2) AS avg_time
            FROM race_result r
            JOIN race_master m ON m.race_id = r.race_id
            WHERE r.time IS NOT NULL AND r.time != ''
            GROUP BY m.venue
        ),
        payout_stats AS (
            SELECT m.venue,
                   ROUND(AVG(p.payout), 0) AS trifecta_avg,
                   MAX(p.payout) AS trifecta_max,
                   ROUND(AVG(CASE WHEN p.payout >= 10000 THEN 100.0 ELSE 0 END), 1) AS high_rate
            FROM payout p
            JOIN race_master m ON m.race_id = p.race_id
            WHERE p.bet_type = ?
            GROUP BY m.venue
        )
        SELECT c.venue, c.races, t.avg_time, p.trifecta_avg, p.trifecta_max, p.high_rate
        FROM race_counts c
        LEFT JOIN time_stats t ON t.venue = c.venue
        LEFT JOIN payout_stats p ON p.venue = c.venue
        ORDER BY c.races DESC, c.venue
    """, (TRIFECTA,))
    medians = median_by_group(conn, "m.venue", "p.payout", """
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = ?
    """, (TRIFECTA,))
    ranking = []
    for row in venue_stats:
        median = medians.get(row["venue"])
        row["trifecta_median_raw"] = median
        score = (row["trifecta_avg"] or 0) + (median or 0) + ((row["high_rate"] or 0) * 100)
        ranking.append({**row, "score": score})

    display_stats = []
    for row in ranking:
        display_stats.append({
            "venue": row["venue"],
            "races": row["races"],
            "avg_time": decimal(row["avg_time"]),
            "trifecta_avg": yen(row["trifecta_avg"]),
            "trifecta_median": yen(row["trifecta_median_raw"]),
            "trifecta_max": yen(row["trifecta_max"]),
            "high_rate": pct(row["high_rate"]),
            "score": f'{row["score"]:.0f}',
        })
    turbulence = sorted(display_stats, key=lambda row: float(row["score"]), reverse=True)

    body = '<div class="grid two">'
    body += section("会場別平均タイム", bar_chart(
        sorted([row for row in ranking if row["avg_time"] is not None], key=lambda row: row["avg_time"]),
        "venue",
        "avg_time",
        lambda v: f"{v:.2f}秒",
    ))
    body += section("会場別3連単平均配当", bar_chart(
        sorted([row for row in ranking if row["trifecta_avg"] is not None], key=lambda row: row["trifecta_avg"], reverse=True),
        "venue",
        "trifecta_avg",
        yen,
    ))
    body += "</div>"
    body += section("会場別統計", table(
        ["会場", "レース数", "平均タイム", "3連単平均", "3連単中央値", "3連単最高", "万車券率", "荒れ度"],
        display_stats,
        ["venue", "races", "avg_time", "trifecta_avg", "trifecta_median", "trifecta_max", "high_rate", "score"],
    ), "件数が少ない会場は参考値として見てください。データ蓄積後に比較精度が上がります。")
    body += section("会場×車番 勝率ヒートマップ", venue_car_heatmap(conn), "色が濃いほど、その会場で1着になった割合が高い車番です。")
    body += section("荒れ度ランキング", table(
        ["会場", "レース数", "3連単平均", "3連単中央値", "万車券率", "荒れ度"],
        turbulence,
        ["venue", "races", "trifecta_avg", "trifecta_median", "high_rate", "score"],
    ))
    return page("会場分析", "venues", body)


def render_car_numbers(conn) -> str:
    stats = rows(conn, """
        SELECT car_no,
               COUNT(*) AS starts,
               SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rank <= 2 THEN 1 ELSE 0 END) AS quinella,
               SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) AS top3,
               ROUND(AVG(rank), 2) AS avg_rank,
               ROUND(SUM(CASE WHEN rank = 1 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS win_rate,
               ROUND(SUM(CASE WHEN rank <= 2 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS quinella_rate,
               ROUND(SUM(CASE WHEN rank <= 3 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM race_result
        WHERE car_no IS NOT NULL
        GROUP BY car_no
        ORDER BY car_no
    """)
    for row in stats:
        row["car_label"] = f'{row["car_no"]}番'
        row["win_rate_display"] = pct(row["win_rate"])
        row["quinella_rate_display"] = pct(row["quinella_rate"])
        row["top3_rate_display"] = pct(row["top3_rate"])
        row["avg_rank_display"] = decimal(row["avg_rank"])
    recovery = car_recovery(conn)

    body = '<div class="grid two">'
    body += section("車番別勝率", bar_chart(stats, "car_label", "win_rate", pct, 9))
    body += section("車番別3着内率", bar_chart(stats, "car_label", "top3_rate", pct, 9))
    body += "</div>"
    body += section("車番別成績", table(
        ["車番", "出走", "1着", "連対", "3着内", "勝率", "連対率", "3着内率", "平均着順"],
        stats,
        ["car_no", "starts", "wins", "quinella", "top3", "win_rate_display", "quinella_rate_display", "top3_rate_display", "avg_rank_display"],
    ))
    body += section("会場×車番 勝率ヒートマップ", venue_car_heatmap(conn))
    body += section("車番別回収率 2車単・100円購入想定", table(
        ["車番", "対象レース", "払戻合計", "投資額", "回収率"],
        recovery,
        ["car_no", "races", "return_total", "investment", "recovery_rate"],
    ))
    return page("車番分析", "cars", body)


def render_payouts(conn) -> str:
    bet_summary = rows(conn, """
        SELECT bet_type,
               COUNT(*) AS count,
               ROUND(AVG(payout), 0) AS avg_payout,
               MAX(payout) AS max_payout,
               ROUND(AVG(CASE WHEN payout >= 10000 THEN 100.0 ELSE 0 END), 1) AS high_rate
        FROM payout
        GROUP BY bet_type
        ORDER BY avg_payout DESC
    """)
    medians = median_by_group(conn, "bet_type", "payout", "FROM payout")
    for row in bet_summary:
        row["median_payout"] = yen(medians.get(row["bet_type"]))
        row["avg_payout_display"] = yen(row["avg_payout"])
        row["max_payout_display"] = yen(row["max_payout"])
        row["high_rate_display"] = pct(row["high_rate"])

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
        SELECT strftime('%Y-%m', m.race_date) AS month,
               ROUND(AVG(p.payout), 0) AS avg_payout
        FROM payout p
        JOIN race_master m ON m.race_id = p.race_id
        WHERE p.bet_type = ?
        GROUP BY month
        ORDER BY month
    """, (TRIFECTA,))
    weekday = rows(conn, """
        SELECT CASE strftime('%w', m.race_date)
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
        WHERE p.bet_type = ?
        GROUP BY strftime('%w', m.race_date)
        ORDER BY strftime('%w', m.race_date)
    """, (TRIFECTA,))
    histogram = payout_histogram(conn)
    for collection in (high, tickets, monthly, weekday, histogram):
        for row in collection:
            if "payout" in row:
                row["payout"] = yen(row["payout"])
            if "avg_payout" in row:
                row["avg_payout_display"] = yen(row["avg_payout"])

    body = '<div class="grid two">'
    body += section("賭式別平均配当", bar_chart(bet_summary, "bet_type", "avg_payout", yen))
    body += section("3連単配当分布", bar_chart(histogram, "range", "count", lambda v: f"{int(v)}件"))
    body += "</div>"
    body += section("賭式別サマリー", table(
        ["賭式", "件数", "平均", "中央値", "最高", "万車券率"],
        bet_summary,
        ["bet_type", "count", "avg_payout_display", "median_payout", "max_payout_display", "high_rate_display"],
    ))
    body += section("高配当ランキング TOP100", table(
        ["日付", "会場", "R", "賭式", "組番", "払戻", "人気"],
        high,
        ["race_date", "venue", "race_no", "bet_type", "combination", "payout", "popularity"],
    ))
    body += section("万車券ランキング", table(
        ["日付", "会場", "R", "賭式", "組番", "払戻", "人気"],
        tickets,
        ["race_date", "venue", "race_no", "bet_type", "combination", "payout", "popularity"],
    ))
    body += '<div class="grid two">'
    body += section("月別3連単平均配当", bar_chart(monthly, "month", "avg_payout", yen, 12))
    body += section("曜日別3連単平均配当", bar_chart(weekday, "weekday", "avg_payout", yen, 7))
    body += "</div>"
    return page("配当分析", "payouts", body)


def render_racers(conn) -> str:
    threshold = racer_threshold(conn)
    base = """
        SELECT racer_name,
               COUNT(*) AS starts,
               SUM(CASE WHEN rank = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rank <= 2 THEN 1 ELSE 0 END) AS quinella,
               SUM(CASE WHEN rank <= 3 THEN 1 ELSE 0 END) AS top3,
               ROUND(AVG(rank), 2) AS avg_rank,
               ROUND(AVG(CAST(NULLIF(time, '') AS REAL)), 2) AS avg_time,
               ROUND(SUM(CASE WHEN rank = 1 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS win_rate,
               ROUND(SUM(CASE WHEN rank <= 2 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS quinella_rate,
               ROUND(SUM(CASE WHEN rank <= 3 THEN 100.0 ELSE 0 END) / COUNT(*), 1) AS top3_rate
        FROM race_result
        WHERE racer_name IS NOT NULL AND racer_name != ''
        GROUP BY racer_name
    """
    starts = rows(conn, base + " ORDER BY starts DESC, racer_name LIMIT 100")
    wins = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= ? ORDER BY win_rate DESC, starts DESC LIMIT 100", (threshold,))
    quinella = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= ? ORDER BY quinella_rate DESC, starts DESC LIMIT 100", (threshold,))
    avg_rank = rows(conn, "SELECT * FROM (" + base + ") WHERE starts >= ? ORDER BY avg_rank ASC, starts DESC LIMIT 100", (threshold,))
    kimarite = rows(conn, """
        SELECT racer_name, kimarite, COUNT(*) AS count
        FROM race_result
        WHERE rank = 1 AND kimarite IS NOT NULL AND kimarite != ''
        GROUP BY racer_name, kimarite
        ORDER BY count DESC
        LIMIT 100
    """)
    for collection in (starts, wins, quinella, avg_rank):
        for row in collection:
            row["win_rate_display"] = pct(row["win_rate"])
            row["quinella_rate_display"] = pct(row["quinella_rate"])
            row["top3_rate_display"] = pct(row["top3_rate"])
            row["avg_rank_display"] = decimal(row["avg_rank"])
            row["avg_time_display"] = decimal(row["avg_time"])

    body = f'<div class="note">ランキング基準: 出走{threshold}回以上。データ蓄積後は自動的に30回以上を基準にします。</div>'
    body += '<div class="grid two">'
    body += section("選手別勝率", bar_chart(wins, "racer_name", "win_rate", pct, 20))
    body += section("選手別平均着順", bar_chart(list(reversed(avg_rank[:20])), "racer_name", "avg_rank", lambda v: f"{v:.2f}"))
    body += "</div>"
    body += section("選手別出走数ランキング", table(
        ["選手", "出走", "1着", "連対", "3着内", "平均着順", "平均タイム"],
        starts,
        ["racer_name", "starts", "wins", "quinella", "top3", "avg_rank_display", "avg_time_display"],
    ))
    body += section("選手別勝率ランキング", table(
        ["選手", "出走", "勝率", "1着", "連対率", "3着内率", "平均着順"],
        wins,
        ["racer_name", "starts", "win_rate_display", "wins", "quinella_rate_display", "top3_rate_display", "avg_rank_display"],
    ))
    body += section("選手別連対率ランキング", table(
        ["選手", "出走", "連対率", "連対", "勝率", "平均着順"],
        quinella,
        ["racer_name", "starts", "quinella_rate_display", "quinella", "win_rate_display", "avg_rank_display"],
    ))
    body += section("選手別決まり手ランキング", table(
        ["選手", "決まり手", "回数"],
        kimarite,
        ["racer_name", "kimarite", "count"],
    ))
    return page("選手分析", "racers", body)


def render_races(conn) -> str:
    race_rows = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, m.event_name, m.race_title,
               m.race_class, m.start_time, m.distance, m.weather,
               CASE WHEN m.wind_speed IS NULL THEN '' ELSE m.wind_speed || 'm/s' END AS wind_speed,
               (
                 SELECT r.car_no
                 FROM race_result r
                 WHERE r.race_id = m.race_id AND r.rank = 1
                 ORDER BY r.id
                 LIMIT 1
               ) AS winner_car,
               (
                 SELECT r.racer_name
                 FROM race_result r
                 WHERE r.race_id = m.race_id AND r.rank = 1
                 ORDER BY r.id
                 LIMIT 1
               ) AS winner,
               p.payout AS trifecta_payout,
               m.lineup_text
        FROM race_master m
        LEFT JOIN payout p ON p.race_id = m.race_id AND p.bet_type = ?
        ORDER BY m.race_date DESC, m.venue, m.race_no
        LIMIT 500
    """, (TRIFECTA,))
    for row in race_rows:
        row["trifecta_payout"] = yen(row["trifecta_payout"])
        row["distance_display"] = "" if row["distance"] is None else f'{row["distance"]}m'
    body = section("取得済みレース一覧", table(
        ["日付", "会場", "R", "開催", "レース名", "級班", "発走", "距離", "天候", "風速", "1着車番", "1着選手", "3連単", "並び"],
        race_rows,
        ["race_date", "venue", "race_no", "event_name", "race_title", "race_class", "start_time", "distance_display", "weather", "wind_speed", "winner_car", "winner", "trifecta_payout", "lineup_text"],
    ), "最新500レースを表示します。分析値が気になったときに、元レースを確認するためのページです。")
    return page("レース一覧", "races", body)


def render_quality(conn) -> str:
    rendered = LOG_DIR / "results_rendered.html"
    log_file = LOG_DIR / "collector.log"
    html_saved_at = "-"
    if rendered.exists():
        html_saved_at = datetime.fromtimestamp(rendered.stat().st_mtime).isoformat(timespec="seconds")
    log_tail = []
    if log_file.exists():
        log_tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
    metrics = [
        {"name": "総レース数", "value": number(scalar(conn, "SELECT COUNT(*) FROM race_master"))},
        {"name": "着順0件のレース", "value": number(scalar(conn, """
            SELECT COUNT(*) FROM race_master m
            WHERE NOT EXISTS (SELECT 1 FROM race_result r WHERE r.race_id = m.race_id)
        """))},
        {"name": "配当0件のレース", "value": number(scalar(conn, """
            SELECT COUNT(*) FROM race_master m
            WHERE NOT EXISTS (SELECT 1 FROM payout p WHERE p.race_id = m.race_id)
        """))},
        {"name": "天候未取得", "value": number(scalar(conn, "SELECT COUNT(*) FROM race_master WHERE weather IS NULL OR weather = ''"))},
        {"name": "風速未取得", "value": number(scalar(conn, "SELECT COUNT(*) FROM race_master WHERE wind_speed IS NULL"))},
        {"name": "並び未取得", "value": number(scalar(conn, "SELECT COUNT(*) FROM race_master WHERE lineup_text IS NULL OR lineup_text = ''"))},
        {"name": "Playwright HTML保存日時", "value": html_saved_at},
    ]
    venue_counts = rows(conn, """
        SELECT venue, COUNT(*) AS races, MIN(race_date) AS first_date, MAX(race_date) AS latest_date
        FROM race_master
        GROUP BY venue
        ORDER BY races DESC, venue
    """)
    log_rows = [{"line": line} for line in log_tail]
    body = section("データ品質サマリー", table(["項目", "値"], metrics, ["name", "value"]))
    body += section("会場別蓄積状況", table(
        ["会場", "レース数", "最初の日付", "最新日付"],
        venue_counts,
        ["venue", "races", "first_date", "latest_date"],
    ))
    body += section("直近ログ", table(["ログ"], log_rows, ["line"]))
    return page("データ品質", "quality", body)


def render_custom(conn) -> str:
    upset = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, r.racer_name, r.rank,
               p.popularity, (p.popularity - r.rank) AS score
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        JOIN payout p ON p.race_id = r.race_id AND p.bet_type = ?
        WHERE p.popularity IS NOT NULL AND r.rank <= 3
        ORDER BY score DESC
        LIMIT 100
    """, (TRIFECTA,))
    fade = rows(conn, """
        SELECT m.race_date, m.venue, m.race_no, r.racer_name, r.rank,
               p.popularity, (r.rank - p.popularity) AS score
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        JOIN payout p ON p.race_id = r.race_id AND p.bet_type = ?
        WHERE p.popularity IS NOT NULL
        ORDER BY score DESC
        LIMIT 100
    """, (TRIFECTA,))
    growth = growth_index(conn)
    yearly = rows(conn, """
        SELECT racer_name, strftime('%Y', m.race_date) AS year, COUNT(*) AS starts
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE racer_name IS NOT NULL AND racer_name != ''
        GROUP BY racer_name, year
        ORDER BY starts DESC
        LIMIT 100
    """)
    body = '<div class="note">人気順位は3連単配当の人気を使った代理指標です。個別選手人気ではないため、参考ランキングとして扱います。</div>'
    body += section("ヘテオジマーベリック指数", table(
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


def payout_histogram(conn) -> list[dict]:
    bins = [
        (0, 999, "999円以下"),
        (1000, 2999, "1,000-2,999円"),
        (3000, 4999, "3,000-4,999円"),
        (5000, 9999, "5,000-9,999円"),
        (10000, 29999, "10,000-29,999円"),
        (30000, 99999, "30,000-99,999円"),
        (100000, None, "100,000円以上"),
    ]
    values = [
        row[0]
        for row in conn.execute("SELECT payout FROM payout WHERE bet_type = ? AND payout IS NOT NULL", (TRIFECTA,))
    ]
    output = []
    for low, high, label in bins:
        if high is None:
            count = sum(1 for value in values if value >= low)
        else:
            count = sum(1 for value in values if low <= value <= high)
        output.append({"range": label, "count": count})
    return output


def car_recovery(conn) -> list[dict]:
    race_count = scalar(conn, "SELECT COUNT(*) FROM race_master")
    returns = defaultdict(int)
    for row in conn.execute("SELECT combination, payout FROM payout WHERE bet_type = '2車単'"):
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


def racer_threshold(conn) -> int:
    enough = scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT racer_name
            FROM race_result
            GROUP BY racer_name
            HAVING COUNT(*) >= 30
        )
    """)
    return 30 if enough >= 10 else 3


def growth_index(conn) -> list[dict]:
    by_racer = defaultdict(list)
    for row in conn.execute("""
        SELECT r.racer_name, r.rank
        FROM race_result r
        JOIN race_master m ON m.race_id = r.race_id
        WHERE r.racer_name IS NOT NULL AND r.racer_name != ''
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
            "races.html": render_races(conn),
            "quality.html": render_quality(conn),
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

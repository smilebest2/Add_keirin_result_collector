import argparse
import html
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, ROOT_DIR
from .db import connect, init_db


DOCS_DIR = ROOT_DIR / "docs"
INDEX_PATH = DOCS_DIR / "index.html"


def h(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def fetch_summary(conn):
    return {
        "races": conn.execute("SELECT COUNT(*) FROM race_master").fetchone()[0],
        "results": conn.execute("SELECT COUNT(*) FROM race_result").fetchone()[0],
        "payouts": conn.execute("SELECT COUNT(*) FROM payout").fetchone()[0],
        "latest_date": conn.execute("SELECT MAX(race_date) FROM race_master").fetchone()[0],
    }


def fetch_races(conn, race_date: str | None = None):
    params = []
    where = ""
    if race_date:
        where = "WHERE race_date = ?"
        params.append(race_date)
    return conn.execute(
        f"""
        SELECT race_id, race_date, venue, race_no, detail_url
        FROM race_master
        {where}
        ORDER BY race_date DESC, venue ASC, race_no ASC
        """,
        params,
    ).fetchall()


def fetch_results(conn, race_id: str):
    return conn.execute(
        """
        SELECT rank, car_no, racer_name, class, prefecture, age, time, kimarite
        FROM race_result
        WHERE race_id = ?
        ORDER BY rank ASC
        """,
        (race_id,),
    ).fetchall()


def fetch_payouts(conn, race_id: str):
    return conn.execute(
        """
        SELECT bet_type, combination, payout
        FROM payout
        WHERE race_id = ?
        ORDER BY id ASC
        """,
        (race_id,),
    ).fetchall()


def render_index(conn, race_date: str | None = None) -> str:
    summary = fetch_summary(conn)
    selected_date = race_date or summary["latest_date"]
    races = fetch_races(conn, selected_date)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    race_cards = []
    for race in races:
        results = fetch_results(conn, race["race_id"])
        payouts = fetch_payouts(conn, race["race_id"])
        result_rows = "\n".join(
            f"""
            <tr>
              <td>{h(row["rank"])}</td>
              <td>{h(row["car_no"])}</td>
              <td>{h(row["racer_name"])}</td>
              <td>{h(row["class"])}</td>
              <td>{h(row["prefecture"])}</td>
              <td>{h(row["age"])}</td>
              <td>{h(row["time"])}</td>
              <td>{h(row["kimarite"])}</td>
            </tr>
            """
            for row in results
        )
        payout_rows = "\n".join(
            f"""
            <tr>
              <td>{h(row["bet_type"])}</td>
              <td>{h(row["combination"])}</td>
              <td>{h(f'{row["payout"]:,}円')}</td>
            </tr>
            """
            for row in payouts
        )
        race_cards.append(
            f"""
            <section class="race" data-venue="{h(race["venue"])}">
              <header class="race-header">
                <div>
                  <h2>{h(race["venue"])} {h(race["race_no"])}R</h2>
                  <p>{h(race["race_id"])}</p>
                </div>
                <a href="{h(race["detail_url"])}" target="_blank" rel="noreferrer">詳細</a>
              </header>
              <div class="tables">
                <div>
                  <h3>レース結果</h3>
                  <table>
                    <thead>
                      <tr>
                        <th>着</th><th>車</th><th>選手名</th><th>級班</th>
                        <th>府県</th><th>年齢</th><th>上り</th><th>決</th>
                      </tr>
                    </thead>
                    <tbody>{result_rows}</tbody>
                  </table>
                </div>
                <div>
                  <h3>払戻</h3>
                  <table>
                    <thead><tr><th>賭式</th><th>組番</th><th>払戻</th></tr></thead>
                    <tbody>{payout_rows}</tbody>
                  </table>
                </div>
              </div>
            </section>
            """
        )

    race_content = "".join(race_cards) if race_cards else """
      <section class="empty">
        <h2>表示できるレース結果はまだありません</h2>
        <p>次回の自動取得後にここへ結果が表示されます。</p>
      </section>
    """

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>競輪レース結果</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --ink: #20242a;
      --muted: #657080;
      --line: #dce1e8;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-soft: #e3f4f1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    header.page {{
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 20px;
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 14px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fbfcfd;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .metric strong {{
      display: block;
      margin-top: 2px;
      font-size: 20px;
    }}
    main {{
      padding: 20px;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 14px;
    }}
    .toolbar input {{
      width: min(360px, 100%);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 11px;
      font-size: 14px;
    }}
    .race {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 14px;
      overflow: hidden;
    }}
    .empty {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      text-align: center;
    }}
    .empty h2 {{
      margin: 0 0 6px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .empty p {{
      margin: 0;
      color: var(--muted);
    }}
    .race-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--accent-soft);
    }}
    .race-header h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .race-header p {{
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
    }}
    .race-header a {{
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
      white-space: nowrap;
    }}
    .tables {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.8fr);
      gap: 16px;
      padding: 16px;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 700;
      background: #fafbfc;
    }}
    @media (max-width: 760px) {{
      .summary {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
      .toolbar {{ align-items: stretch; flex-direction: column; }}
      .tables {{ grid-template-columns: 1fr; overflow-x: auto; }}
      table {{ min-width: 620px; }}
    }}
  </style>
</head>
<body>
  <header class="page">
    <div class="wrap">
      <h1>競輪レース結果</h1>
      <div class="summary">
        <div class="metric"><span>表示日</span><strong>{h(selected_date or "-")}</strong></div>
        <div class="metric"><span>累計レース</span><strong>{h(summary["races"])}</strong></div>
        <div class="metric"><span>選手結果</span><strong>{h(summary["results"])}</strong></div>
        <div class="metric"><span>払戻</span><strong>{h(summary["payouts"])}</strong></div>
      </div>
    </div>
  </header>
  <main>
    <div class="wrap">
      <div class="toolbar">
        <span>{h(len(races))}レース / generated at {h(generated_at)}</span>
        <input id="filter" type="search" placeholder="会場名で絞り込み">
      </div>
      {race_content}
    </div>
  </main>
  <script>
    const input = document.getElementById("filter");
    const races = Array.from(document.querySelectorAll(".race"));
    input.addEventListener("input", () => {{
      const keyword = input.value.trim();
      for (const race of races) {{
        race.hidden = keyword && !race.dataset.venue.includes(keyword);
      }}
    }});
  </script>
</body>
</html>
"""


def export_html(race_date: str | None = None, output_path: Path = INDEX_PATH) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with connect(DB_PATH) as conn:
        init_db(conn)
        output_path.write_text(render_index(conn, race_date), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export collected keirin results to static HTML")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD. Default: latest date in DB")
    args = parser.parse_args()
    path = export_html(args.date)
    print(f"Exported {path}")


if __name__ == "__main__":
    main()

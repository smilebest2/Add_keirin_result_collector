import argparse
import logging
from datetime import date, datetime
from time import sleep

import requests

from .config import HEADERS, LOG_DIR, REQUEST_RETRY, REQUEST_TIMEOUT, RESULTS_URL
from .db import connect, init_db, race_exists, save_race
from .parser import extract_payouts, extract_race_meta, extract_race_results, extract_result_links


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "collector.log", mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    error_handler = logging.FileHandler(LOG_DIR / "error.log", mode="w", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(error_handler)


def fetch_html(url: str, retry: int = REQUEST_RETRY) -> str:
    last_error = None
    for attempt in range(1, retry + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            logging.warning("Fetch failed (%s/%s): %s", attempt, retry, url)
            sleep(attempt)
    raise RuntimeError(f"Failed to fetch {url}") from last_error


def collect(target_date: str | None = None) -> dict:
    target_date = target_date or date.today().isoformat()
    logging.info("Collecting keirin results for %s", target_date)
    list_html = fetch_html(RESULTS_URL)
    links = extract_result_links(list_html)
    logging.info("Found %s result links", len(links))

    stats = {"found": len(links), "saved": 0, "skipped": 0, "failed": 0}
    with connect() as conn:
        init_db(conn)
        for link in links:
            try:
                detail_html = fetch_html(link.url)
                race = extract_race_meta(detail_html, link.url)
                if race["race_date"] != target_date:
                    stats["skipped"] += 1
                    continue
                if race_exists(conn, race["race_id"]):
                    stats["skipped"] += 1
                    logging.info("Skip existing race: %s", race["race_id"])
                    continue

                results = extract_race_results(detail_html)
                payouts = extract_payouts(detail_html)
                save_race(conn, race, results, payouts)
                stats["saved"] += 1
                logging.info("Saved race: %s", race["race_id"])
            except Exception:
                stats["failed"] += 1
                logging.exception("Failed to collect detail: %s", link.url)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect WINTICKET keirin race results")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD. Default: today")
    args = parser.parse_args()
    setup_logging()
    stats = collect(args.date)
    logging.info("Completed: %s", stats)


if __name__ == "__main__":
    main()

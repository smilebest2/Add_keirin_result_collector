import argparse
import logging
from datetime import date, datetime
from time import sleep

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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


def fetch_rendered_html(url: str, output_path, retry: int = REQUEST_RETRY) -> str:
    last_error = None
    for attempt in range(1, retry + 1):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=HEADERS["User-Agent"],
                    viewport={"width": 1366, "height": 900},
                )
                page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
                try:
                    page.wait_for_selector('a[href*="/raceresult/"]', timeout=10_000)
                except PlaywrightTimeoutError:
                    logging.warning("Rendered result links were not visible yet: %s", url)
                html = page.content()
                browser.close()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html, encoding="utf-8")
            return html
        except Exception as exc:
            last_error = exc
            logging.warning("Rendered fetch failed (%s/%s): %s", attempt, retry, url)
            sleep(attempt)
    raise RuntimeError(f"Failed to render {url}") from last_error


def collect(target_date: str | None = None) -> dict:
    target_date = target_date or date.today().isoformat()
    logging.info("Collecting keirin results for %s", target_date)
    list_html = fetch_rendered_html(RESULTS_URL, LOG_DIR / "results_rendered.html")
    links = extract_result_links(list_html)
    logging.info("Found %s result links", len(links))
    if not links:
        raise RuntimeError("No result links were found in rendered results page")

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

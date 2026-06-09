import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .config import BASE_URL, VENUE_CODES


DETAIL_RE = re.compile(r"/keirin/[^/]+/raceresult/(\d{10})/(\d+)/(\d+)")
DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
START_TIME_RE = re.compile(r"発走\s*(\d{1,2}:\d{2})")
RACE_NO_RE = re.compile(r"/(\d+)$")
RACER_RE = re.compile(
    r"(?P<name>[^\s]+)\s+(?P<prefecture>[^\s]+)\s+(?P<class>[ASL]\d?)\s+"
    r"(?P<age>\d{1,2})歳"
)
PAYOUT_RE = re.compile(
    r"^(?P<type>2枠複|2枠単|2車複|2車単|3連複|3連単|ワイド)\s+"
    r"(?P<combination>[0-9=\-]+)\s+(?P<payout>[\d,]+)\s*円"
)


@dataclass(frozen=True)
class RaceLink:
    url: str
    race_no: int


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_japanese_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    return date(year, month, day).isoformat()


def extract_result_links(html: str) -> list[RaceLink]:
    soup = soup_from_html(html)
    links: list[RaceLink] = []
    seen = set()
    for anchor in soup.select('a[href*="/raceresult/"]'):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(BASE_URL, href)
        parsed_path = urlparse(url).path
        match = DETAIL_RE.search(parsed_path)
        if not match:
            continue
        race_no = int(match.group(3))
        if url in seen:
            continue
        seen.add(url)
        links.append(RaceLink(url=url, race_no=race_no))
    return links


def extract_race_meta(html: str, detail_url: str) -> dict:
    soup = soup_from_html(html)
    page_text = "\n".join(soup.stripped_strings)
    path = urlparse(detail_url).path
    url_match = DETAIL_RE.search(path)
    if not url_match:
        raise ValueError(f"Unsupported detail URL: {detail_url}")

    race_date = parse_japanese_date(page_text)
    start_time = parse_start_time(page_text)
    venue = _extract_venue(soup, page_text)
    race_no = int(url_match.group(3))
    race_id = build_race_id(race_date, venue, race_no, detail_url)

    return {
        "race_id": race_id,
        "race_date": race_date,
        "venue": venue,
        "race_no": race_no,
        "start_time": start_time,
        "detail_url": detail_url,
    }


def parse_start_time(text: str) -> str | None:
    match = START_TIME_RE.search(text)
    if not match:
        return None
    return match.group(1)


def build_race_id(race_date: str | None, venue: str | None, race_no: int, detail_url: str) -> str:
    path = urlparse(detail_url).path
    url_match = DETAIL_RE.search(path)
    event_id = url_match.group(1) if url_match else ""
    date_part = race_date.replace("-", "") if race_date else event_id[:8]
    venue_code = VENUE_CODES.get(venue or "", _venue_code_from_url(detail_url))
    return f"{date_part}_{venue_code}_{race_no:02d}"


def extract_race_results(html: str) -> list[dict]:
    soup = soup_from_html(html)
    table_results = _extract_result_rows_from_tables(soup)
    if table_results:
        return table_results

    lines = [normalize_text(text) for text in soup.stripped_strings]
    results: list[dict] = []
    i = _find_result_table_start(lines)

    while i < len(lines):
        if lines[i] == "払戻金":
            break
        if _is_rank_line(lines, i):
            rank = int(lines[i])
            car_no = int(lines[i + 1])
            racer_match = RACER_RE.search(lines[i + 2])
            if racer_match:
                time_value, kimarite = _extract_time_and_kimarite(lines, i + 3)
                results.append(
                    {
                        "rank": rank,
                        "car_no": car_no,
                        "racer_name": racer_match.group("name"),
                        "class": racer_match.group("class"),
                        "prefecture": racer_match.group("prefecture"),
                        "age": int(racer_match.group("age")),
                        "time": time_value,
                        "kimarite": kimarite,
                    }
                )
                i += 4
                continue
        i += 1

    if not results:
        raise ValueError("Race result rows were not found")
    return results


def extract_payouts(html: str) -> list[dict]:
    soup = soup_from_html(html)
    table_payouts = _extract_payout_rows_from_tables(soup)
    if table_payouts:
        return table_payouts

    lines = [normalize_text(text) for text in soup.stripped_strings]
    try:
        start = lines.index("払戻金")
    except ValueError:
        return []

    payouts: list[dict] = []
    active_wide = False
    for line in lines[start + 1 :]:
        if line.startswith("## ") or line == "オッズ一覧":
            break
        match = PAYOUT_RE.search(line)
        if match:
            bet_type = match.group("type")
            active_wide = bet_type == "ワイド"
            payouts.append(_payout_from_match(match))
            continue

        if active_wide:
            wide_match = re.search(r"^(?P<combination>[0-9=]+)\s+(?P<payout>[\d,]+)\s*円", line)
            if wide_match:
                payouts.append(
                    {
                        "bet_type": "ワイド",
                        "combination": wide_match.group("combination"),
                        "payout": int(wide_match.group("payout").replace(",", "")),
                    }
                )
    return payouts


def _extract_venue(soup: BeautifulSoup, page_text: str) -> str | None:
    title = soup.find("title")
    candidates = []
    if title and title.string:
        candidates.append(title.string)
    candidates.append(page_text)

    for text in candidates:
        match = re.search(r"([^\s]+)競輪", text)
        if match:
            return match.group(1)
    return None


def _extract_result_rows_from_tables(soup: BeautifulSoup) -> list[dict]:
    results: list[dict] = []
    for row in soup.select("tr"):
        cells = [normalize_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) < 5 or not cells[0].isdigit() or not cells[1].isdigit():
            continue
        racer_link = row.select_one('a[href*="/keirin/cyclist/"]')
        if not racer_link:
            continue
        racer_name = normalize_text(racer_link.get_text(" ", strip=True))
        prefecture, racer_class, age = _parse_player_meta(cells, racer_name)
        time_value = next((cell for cell in cells[4:] if re.fullmatch(r"\d{1,2}\.\d", cell)), None)
        kimarite = next((cell for cell in cells[4:] if re.fullmatch(r"(逃|捲|差|マ)", cell)), None)
        results.append(
            {
                "rank": int(cells[0]),
                "car_no": int(cells[1]),
                "racer_name": racer_name,
                "class": racer_class,
                "prefecture": prefecture,
                "age": age,
                "time": time_value,
                "kimarite": kimarite,
            }
        )
    return results


def _extract_payout_rows_from_tables(soup: BeautifulSoup) -> list[dict]:
    payouts: list[dict] = []
    current_bet_type = None
    known_types = {"2枠複", "2枠単", "2車複", "2車単", "3連複", "3連単", "ワイド"}

    for row in soup.select("tr"):
        cells = [normalize_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        if cells[0] in known_types:
            current_bet_type = cells[0]
            if "未発売" in cells:
                continue
            parsed = _parse_payout_cells(current_bet_type, cells[1:])
            if parsed:
                payouts.append(parsed)
            continue
        if current_bet_type == "ワイド":
            parsed = _parse_payout_cells("ワイド", cells)
            if parsed:
                payouts.append(parsed)
    return payouts


def _parse_player_meta(cells: list[str], racer_name: str) -> tuple[str | None, str | None, int | None]:
    for cell in cells:
        meta_text = cell.replace(racer_name, "", 1).strip()
        meta_match = re.search(r"(?P<prefecture>\S+)\s+(?P<class>[ASL]\d?)\s+(?P<age>\d{1,2})歳", meta_text)
        if meta_match:
            return (
                meta_match.group("prefecture"),
                meta_match.group("class"),
                int(meta_match.group("age")),
            )
    return None, None, None


def _parse_payout_cells(bet_type: str, cells: list[str]) -> dict | None:
    combination = next((cell for cell in cells if re.fullmatch(r"\d+(?:[=\-]\d+)+", cell)), None)
    payout_text = next((cell for cell in cells if re.fullmatch(r"[\d,]+\s*円?", cell)), None)
    if not combination or not payout_text:
        return None
    return {
        "bet_type": bet_type,
        "combination": combination,
        "payout": int(re.sub(r"\D", "", payout_text)),
    }


def _venue_code_from_url(detail_url: str) -> str:
    parts = [part for part in urlparse(detail_url).path.split("/") if part]
    if len(parts) >= 2:
        return parts[1].upper()
    return "UNKNOWN"


def _find_result_table_start(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.startswith("着 車 選手名"):
            return index + 1
    return 0


def _is_rank_line(lines: list[str], index: int) -> bool:
    return (
        index + 2 < len(lines)
        and re.fullmatch(r"\d+", lines[index] or "") is not None
        and re.fullmatch(r"\d+", lines[index + 1] or "") is not None
        and RACER_RE.search(lines[index + 2] or "") is not None
    )


def _extract_time_and_kimarite(lines: list[str], index: int) -> tuple[str | None, str | None]:
    if index >= len(lines):
        return None, None
    time_match = re.search(r"\d{1,2}\.\d", lines[index])
    kimarite_match = re.search(r"(逃|捲|差|マ|追|切|失|落|棄)", lines[index])
    return (
        time_match.group(0) if time_match else None,
        kimarite_match.group(0) if kimarite_match else None,
    )


def _payout_from_match(match: re.Match) -> dict:
    return {
        "bet_type": match.group("type"),
        "combination": match.group("combination"),
        "payout": int(match.group("payout").replace(",", "")),
    }

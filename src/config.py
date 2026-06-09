from pathlib import Path


BASE_URL = "https://www.winticket.jp"
RESULTS_URL = f"{BASE_URL}/keirin/results"

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
DB_PATH = DATA_DIR / "keirin.db"

REQUEST_TIMEOUT = 20
REQUEST_RETRY = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

VENUE_CODES = {
    "函館": "HAK",
    "青森": "AOM",
    "いわき平": "IWA",
    "弥彦": "YAH",
    "前橋": "MAE",
    "取手": "TOR",
    "宇都宮": "UTS",
    "大宮": "OMI",
    "西武園": "SEI",
    "京王閣": "KEI",
    "立川": "TAC",
    "松戸": "MAT",
    "千葉": "CHI",
    "川崎": "KAW",
    "平塚": "HIRATSUKA",
    "小田原": "ODA",
    "伊東": "ITO",
    "静岡": "SHI",
    "名古屋": "NAG",
    "岐阜": "GIF",
    "大垣": "OGA",
    "豊橋": "TOYOHASHI",
    "富山": "TOYAMA",
    "松阪": "MATSU",
    "四日市": "YOK",
    "福井": "FUK",
    "奈良": "NAR",
    "向日町": "MUK",
    "和歌山": "WAK",
    "岸和田": "KIS",
    "玉野": "TAM",
    "広島": "HIROSHIMA",
    "防府": "HOF",
    "高松": "TAKAMATSU",
    "小松島": "KOM",
    "高知": "KOC",
    "松山": "MATY",
    "小倉": "KOK",
    "久留米": "KUR",
    "武雄": "TAKEO",
    "佐世保": "SAS",
    "別府": "BEF",
    "熊本": "KUM",
}

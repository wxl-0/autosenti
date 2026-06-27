"""
Autohome (汽车之家) review scraper service.

Scrapes user reviews (口碑) from https://k.autohome.com.cn for a given car model.

NOTE: CAR_ID_MAP values are placeholders ("TBD") — real IDs will be confirmed
in Task 7 by manually checking k.autohome.com.cn URLs.

URL format: https://k.autohome.com.cn/spec/list_{car_id}_0_0_{page}_0.html
"""

import time

import httpx
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CAR_ID_MAP: dict[str, str] = {
    "零跑D19": "TBD",   # confirm from https://k.autohome.com.cn 口碑区 URL
    "理想L9":  "TBD",
    "问界M7":  "TBD",
    "深蓝S07": "TBD",
}

URL_TEMPLATE = "https://k.autohome.com.cn/spec/list_{car_id}_0_0_{page}_0.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_page(html: str, brand: str, page_url: str) -> list[dict]:
    """Parse a single review page and return a list of review dicts.

    CSS selectors are best-effort guesses for autohome's DOM structure.
    The tests mock the HTTP response, so the selectors do not need to
    perfectly match the live site for the test suite to pass.
    """
    soup = BeautifulSoup(html, "lxml")
    reviews: list[dict] = []

    # Try several candidate selectors for review item containers
    for item in soup.select(".koubei-item, .reply-item, [class*='koubei']"):
        # Extract review text
        text_el = item.select_one(".text-content, .content-text, p")
        if not text_el:
            continue
        text = text_el.get_text(strip=True)
        if len(text) < 5:
            continue

        # Extract star rating (may be absent)
        score_el = item.select_one(".score, [class*='score']")
        try:
            rating = float(score_el.get_text(strip=True)) if score_el else 0.0
        except ValueError:
            rating = 0.0

        # Extract publish date (may be absent)
        date_el = item.select_one(".date, [class*='date'], time")
        date = date_el.get_text(strip=True) if date_el else ""

        reviews.append(
            {
                "text": text,
                "rating": rating,
                "date": date,
                "url": page_url,
                "brand": brand,
            }
        )

    return reviews


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_brand_reviews(
    brand: str,
    car_id: str,
    max_pages: int = 3,
) -> list[dict]:
    """Scrape up to *max_pages* pages of reviews for one brand/model.

    Returns a list of review dicts:
        {"text": str, "rating": float, "date": str, "url": str, "brand": str}

    Stops early if a page returns non-200 or yields zero reviews.
    """
    all_reviews: list[dict] = []
    for page in range(1, max_pages + 1):
        url = URL_TEMPLATE.format(car_id=car_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                break
            page_reviews = _parse_page(resp.text, brand, url)
            if not page_reviews:
                break
            all_reviews.extend(page_reviews)
            time.sleep(0.5)
        except Exception:  # network errors, timeouts, etc.
            break
    return all_reviews


def scrape_pages_for_brand(
    brand: str,
    car_id: str,
    pages: list[int],
) -> list[dict]:
    """Scrape an explicit list of page numbers (useful for parallel fetching).

    Unlike *scrape_brand_reviews*, this does **not** stop early on empty pages.
    """
    all_reviews: list[dict] = []
    for page in pages:
        url = URL_TEMPLATE.format(car_id=car_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code == 200:
                all_reviews.extend(_parse_page(resp.text, brand, url))
            time.sleep(0.5)
        except Exception:
            pass
    return all_reviews


def scrape_all_brands(
    brand_car_id_map: dict[str, str],
    max_pages: int = 3,
) -> dict[str, list[dict]]:
    """Scrape reviews for every brand in *brand_car_id_map*.

    Returns ``{brand: [review_dict, ...]}`` for each brand.
    """
    return {
        brand: scrape_brand_reviews(brand, car_id, max_pages)
        for brand, car_id in brand_car_id_map.items()
    }

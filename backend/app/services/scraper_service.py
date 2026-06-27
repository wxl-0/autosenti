"""
Autohome (汽车之家) review scraper service.

Scrapes user reviews (口碑) from https://k.autohome.com.cn for a given car model.

URL format (series-level 口碑 pages):
  https://k.autohome.com.cn/{series_id}/index_{page}.html

Selectors verified against live DOM (2026-06-27):
  container : li.clearfix
  text      : [class*="kb_msg"]
  rating    : [class*="custom_rank"]  → "综合口碑评分\n4.57"
  date      : [class*="timeline"]     → "2026-06-14 发表口碑"
"""

import re
import time

import httpx
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CAR_ID_MAP: dict[str, str] = {
    "零跑D19": "8273",
    "理想L9":  "6576",
    "蔚来ES6": "4881",
    "深蓝S07": "6817",
}

URL_TEMPLATE = "https://k.autohome.com.cn/{series_id}/index_{page}.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

_RATING_RE = re.compile(r"\d+\.\d+")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_page(html: str, brand: str, page_url: str) -> list[dict]:
    """Parse a single review page and return a list of review dicts."""
    soup = BeautifulSoup(html, "lxml")
    reviews: list[dict] = []

    for item in soup.select("li.clearfix"):
        text_el = item.select_one("[class*='kb_msg']")
        if not text_el:
            continue
        text = text_el.get_text(strip=True)
        if len(text) < 5:
            continue

        score_el = item.select_one("[class*='custom_rank']")
        rating = 0.0
        if score_el:
            m = _RATING_RE.search(score_el.get_text())
            if m:
                try:
                    rating = float(m.group())
                except ValueError:
                    pass

        date_el = item.select_one("[class*='timeline']")
        date = ""
        if date_el:
            date = date_el.get_text(strip=True).replace("发表口碑", "").strip()

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
    series_id: str,
    max_pages: int = 3,
) -> list[dict]:
    """Scrape up to *max_pages* pages of reviews for one brand/model.

    Returns a list of review dicts:
        {"text": str, "rating": float, "date": str, "url": str, "brand": str}

    Stops early if a page returns non-200 or yields zero reviews.
    """
    all_reviews: list[dict] = []
    for page in range(1, max_pages + 1):
        url = URL_TEMPLATE.format(series_id=series_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                break
            page_reviews = _parse_page(resp.text, brand, url)
            if not page_reviews:
                break
            all_reviews.extend(page_reviews)
            time.sleep(0.5)
        except Exception:
            break
    return all_reviews


def scrape_pages_for_brand(
    brand: str,
    series_id: str,
    pages: list[int],
) -> list[dict]:
    """Scrape an explicit list of page numbers (useful for ReAct top-up)."""
    all_reviews: list[dict] = []
    for page in pages:
        url = URL_TEMPLATE.format(series_id=series_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code == 200:
                all_reviews.extend(_parse_page(resp.text, brand, url))
            time.sleep(0.5)
        except Exception:
            pass
    return all_reviews


def scrape_all_brands(
    brand_series_id_map: dict[str, str],
    max_pages: int = 3,
) -> dict[str, list[dict]]:
    """Scrape reviews for every brand in *brand_series_id_map*.

    Returns ``{brand: [review_dict, ...]}`` for each brand.
    """
    return {
        brand: scrape_brand_reviews(brand, series_id, max_pages)
        for brand, series_id in brand_series_id_map.items()
    }

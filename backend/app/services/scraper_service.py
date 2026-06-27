"""
Autohome (汽车之家) review scraper service.

Calls the Autohome JSON API directly instead of parsing HTML,
because the 口碑 pages are Next.js CSR apps that render via client-side JS.

API endpoint (verified 2026-06-27 via network interception):
  https://koubeiipv6.app.autohome.com.cn/pc/series/list
  ?pm=3&seriesId={series_id}&pageIndex={page}&pageSize=20
  &yearid=0&ge=0&seriesSummaryKey=0&order=0

Response shape:
  result.list[]
    .contents[]          – [{structuredname: "满意"|"不满意", content: str}]
    .feeling_summary     – one-line summary string
    .scoreList[]         – [{name: "空间"|"续航"|..., value: "1"-"5"}]
    .posttime            – "YYYY-MM-DD"
    .averageScore        – float
  result.pagecount       – total pages
  result.rowcount        – total reviews
"""

import time

import httpx


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CAR_ID_MAP: dict[str, str] = {
    "零跑D19": "8273",
    "理想L9":  "6576",
    "蔚来ES6": "4881",
    "深蓝S07": "6817",
}

API_URL = (
    "https://koubeiipv6.app.autohome.com.cn/pc/series/list"
    "?pm=3&seriesId={series_id}&pageIndex={page}&pageSize=20"
    "&yearid=0&ge=0&seriesSummaryKey=0&order=0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://k.autohome.com.cn/",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_item(item: dict, brand: str) -> dict | None:
    """Convert a single API review object into our canonical review dict."""
    contents = item.get("contents") or []
    text_parts = []
    for c in contents:
        name = c.get("structuredname", "")
        content = c.get("content", "").strip()
        if content:
            text_parts.append(f"[{name}] {content}" if name else content)

    # Fall back to feeling_summary if contents is empty
    if not text_parts:
        summary = (item.get("feeling_summary") or "").strip()
        if summary:
            text_parts.append(summary)

    text = " ".join(text_parts)
    if len(text) < 5:
        return None

    avg_score = item.get("averageScore") or 0.0
    try:
        rating = float(avg_score)
    except (TypeError, ValueError):
        rating = 0.0

    date = item.get("posttime", "")

    score_list = item.get("scoreList") or []
    scores: dict[str, int] = {}
    for s in score_list:
        name = s.get("name", "")
        val = s.get("value")
        if name and val:
            try:
                scores[name] = int(val)
            except (ValueError, TypeError):
                pass

    return {
        "text": text,
        "rating": rating,
        "date": date,
        "brand": brand,
        "scores": scores,  # e.g. {"空间": 5, "续航": 4, "驾驶感受": 4, ...}
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_brand_reviews(
    brand: str,
    series_id: str,
    max_pages: int = 3,
) -> list[dict]:
    """Fetch up to *max_pages* pages of reviews for one brand/model via API.

    Returns a list of review dicts:
        {"text": str, "rating": float, "date": str, "brand": str}

    Stops early if the API returns no items or indicates no more pages.
    """
    assert series_id != "TBD", f"series_id for {brand!r} not configured"

    all_reviews: list[dict] = []
    for page in range(1, max_pages + 1):
        url = API_URL.format(series_id=series_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                break
            data = resp.json()
            result = data.get("result") or {}
            items = result.get("list") or []
            if not items:
                break
            for item in items:
                parsed = _parse_item(item, brand)
                if parsed:
                    all_reviews.append(parsed)
            page_count = result.get("pagecount", 0)
            if page >= page_count:
                break
            time.sleep(0.5)
        except Exception:
            break
    return all_reviews


def scrape_pages_for_brand(
    brand: str,
    series_id: str,
    pages: list[int],
) -> list[dict]:
    """Fetch an explicit list of page numbers (used for ReAct top-up)."""
    all_reviews: list[dict] = []
    for page in pages:
        url = API_URL.format(series_id=series_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get("result") or {}).get("list") or []
                for item in items:
                    parsed = _parse_item(item, brand)
                    if parsed:
                        all_reviews.append(parsed)
            time.sleep(0.5)
        except Exception:
            pass
    return all_reviews


def scrape_all_brands(
    brand_series_id_map: dict[str, str],
    max_pages: int = 3,
) -> dict[str, list[dict]]:
    """Fetch reviews for every brand in *brand_series_id_map*.

    Returns ``{brand: [review_dict, ...]}`` for each brand.
    """
    return {
        brand: scrape_brand_reviews(brand, series_id, max_pages)
        for brand, series_id in brand_series_id_map.items()
    }

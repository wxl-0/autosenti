import pytest
from unittest.mock import patch, MagicMock
from app.services.scraper_service import scrape_brand_reviews, scrape_all_brands, CAR_ID_MAP


def make_mock_html(reviews: list[dict]) -> str:
    """Build HTML that matches the live autohome DOM structure (li.clearfix)."""
    items = ""
    for r in reviews:
        items += f"""
        <li class="clearfix">
          <div class="list_kb_msg__U76oD">{r['text']}</div>
          <div class="list_custom_rank__4x4Iv">综合口碑评分\n{r.get('rating', 4.5)}</div>
          <p class="list_timeline__1N6pP">{r.get('date', '2024-01-01')} 发表口碑</p>
        </li>
        """
    return f"<html><body><ul>{items}</ul></body></html>"


@patch("app.services.scraper_service.httpx")
def test_scrape_brand_reviews_returns_list(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = make_mock_html([
        {"text": "空间很大，后排宽敞", "rating": 4.5, "date": "2024-01-15"}
    ])
    mock_httpx.get.return_value = mock_response

    result = scrape_brand_reviews("零跑D19", "8273", max_pages=1)

    assert isinstance(result, list)
    assert len(result) >= 1
    assert "text" in result[0]
    assert "url" in result[0]
    assert "brand" in result[0]
    assert result[0]["brand"] == "零跑D19"
    assert result[0]["rating"] == 4.5
    assert result[0]["date"] == "2024-01-15"


@patch("app.services.scraper_service.httpx")
def test_scrape_all_brands_returns_dict(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = make_mock_html([{"text": "好车", "rating": 5.0, "date": "2024-01-01"}])
    mock_httpx.get.return_value = mock_response

    result = scrape_all_brands({"品牌A": "11111"}, max_pages=1)

    assert isinstance(result, dict)
    assert "品牌A" in result
    assert isinstance(result["品牌A"], list)


def test_car_id_map_structure():
    assert isinstance(CAR_ID_MAP, dict)
    assert len(CAR_ID_MAP) >= 4
    for brand, series_id in CAR_ID_MAP.items():
        assert isinstance(brand, str)
        assert isinstance(series_id, str)
        assert series_id != "TBD", f"{brand} still has TBD series_id"

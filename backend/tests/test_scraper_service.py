import pytest
from unittest.mock import patch, MagicMock
from app.services.scraper_service import scrape_brand_reviews, scrape_all_brands, CAR_ID_MAP


def make_mock_html(reviews: list[dict]) -> str:
    items = ""
    for r in reviews:
        items += f"""
        <div class="koubei-list-wrapper">
          <div class="koubei-item">
            <div class="text-content">{r['text']}</div>
            <div class="score">{r.get('rating', 4.5)}</div>
            <div class="date">{r.get('date', '2024-01-01')}</div>
          </div>
        </div>
        """
    return f"<html><body>{items}</body></html>"


@patch("app.services.scraper_service.httpx")
def test_scrape_brand_reviews_returns_list(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = make_mock_html([
        {"text": "空间很大，后排宽敞", "rating": 4.5, "date": "2024-01-15"}
    ])
    mock_httpx.get.return_value = mock_response

    result = scrape_brand_reviews("零跑D19", "12345", max_pages=1)

    assert isinstance(result, list)
    assert len(result) >= 1
    assert "text" in result[0]
    assert "url" in result[0]
    assert "brand" in result[0]
    assert result[0]["brand"] == "零跑D19"


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
    for brand, car_id in CAR_ID_MAP.items():
        assert isinstance(brand, str)
        assert isinstance(car_id, str)

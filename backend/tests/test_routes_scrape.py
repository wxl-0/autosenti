import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app


client = TestClient(app)


def test_scrape_endpoint_exists():
    # 用错误的 body 触发 422，确认路由已注册（如果返回 404 则路由未注册）
    res = client.post("/api/scrape", json={})
    assert res.status_code != 404, "Route /api/scrape not registered"


@patch("app.api.routes_scrape.run_analysis_workflow", new_callable=AsyncMock)
def test_scrape_returns_run_id(mock_workflow):
    mock_workflow.return_value = {
        "run_id": 1,
        "report_markdown": "# 报告",
        "final_output": "分析完成",
        "interception_suggestions": [],
        "has_interception_opportunity": False,
    }
    res = client.post("/api/scrape", json={
        "target_brand": "零跑D19",
        "competitor_brands": ["理想L9"],
        "max_pages": 1,
        "conversation_id": "test-conv",
    })
    assert res.status_code == 200
    data = res.json()
    assert "report_markdown" in data
    assert "final_output" in data


def test_reports_endpoint_exists():
    res = client.get("/api/scrape/reports")
    assert res.status_code != 404

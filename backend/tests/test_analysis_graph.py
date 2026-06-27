import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import AgentRun
from app.agents.analysis_graph import run_analysis_workflow


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


MOCK_REVIEWS = {
    "零跑D19": [
        {"text": "空间很大，后排非常宽敞，三人坐不挤", "rating": 4.5, "date": "2024-01-01", "url": "http://test", "brand": "零跑D19"},
        {"text": "车机偶尔卡顿，但可以接受", "rating": 3.5, "date": "2024-01-02", "url": "http://test", "brand": "零跑D19"},
    ],
    "理想L9": [
        {"text": "空间体验绝对一流，冰箱彩电大沙发", "rating": 5.0, "date": "2024-01-01", "url": "http://test", "brand": "理想L9"},
    ],
}


@patch("app.agents.analysis_graph.scrape_all_brands")
@patch("app.agents.analysis_graph.call_llm")
def test_workflow_runs_to_completion(mock_llm, mock_scrape):
    mock_scrape.return_value = MOCK_REVIEWS
    mock_llm.return_value = {
        "dimensions": ["空间体验", "车机系统"],
        "target_weaknesses": [],
        "competitor_advantages": [{"dimension": "空间体验", "competitor": "理想L9", "gap": 0.3}],
        "content_gaps": [],
        "has_interception_opportunity": True,
        "interception_angle": "性价比切入",
        "content_format": "图文",
        "evidence_quotes": ["空间很大"],
        "priority": "high",
    }
    db = make_db()
    state = asyncio.get_event_loop().run_until_complete(
        run_analysis_workflow(db, "零跑D19", ["理想L9"], max_pages=1, conversation_id="test")
    )
    assert state.get("report_markdown")
    assert state.get("final_output")
    assert "has_interception_opportunity" in state
    db.close()


@patch("app.agents.analysis_graph.scrape_all_brands")
@patch("app.agents.analysis_graph.call_llm")
def test_workflow_skips_interception_when_no_opportunity(mock_llm, mock_scrape):
    mock_scrape.return_value = MOCK_REVIEWS
    mock_llm.return_value = {
        "dimensions": ["空间体验"],
        "target_weaknesses": [],
        "competitor_advantages": [],
        "content_gaps": [],
        "has_interception_opportunity": False,
    }
    db = make_db()
    state = asyncio.get_event_loop().run_until_complete(
        run_analysis_workflow(db, "零跑D19", ["理想L9"], max_pages=1, conversation_id="test")
    )
    assert state.get("has_interception_opportunity") is False
    assert state.get("report_markdown")
    db.close()

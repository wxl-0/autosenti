from app.db.database import Base
from app.db.models import SentimentAlert, FeedbackItem
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session


def get_test_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_sentiment_alert_table_exists():
    engine = get_test_engine()
    inspector = inspect(engine)
    assert "sentiment_alerts" in inspector.get_table_names()


def test_sentiment_alert_columns():
    engine = get_test_engine()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("sentiment_alerts")}
    required = {"id", "conversation_id", "target_brand", "competitor_brand",
                "dimension", "gap_type", "severity", "interception_angle",
                "evidence_quotes", "content_format", "priority_rank", "created_at"}
    assert required.issubset(cols)


def test_feedback_item_has_source_url():
    engine = get_test_engine()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("feedback_items")}
    assert "source_url" in cols


def test_create_sentiment_alert():
    engine = get_test_engine()
    with Session(engine) as db:
        alert = SentimentAlert(
            conversation_id="test-conv",
            target_brand="零跑D19",
            competitor_brand="理想L9",
            dimension="空间体验",
            gap_type="competitor_advantage",
            severity="high",
            interception_angle="从性价比切入",
            evidence_quotes='["后排宽敞"]',
            content_format="图文对比",
            priority_rank=1,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        assert alert.id is not None
        assert alert.target_brand == "零跑D19"

from app.agents.state import AnalysisState
from app.core.prompt_loader import get_system_prompt


def test_analysis_state_is_typeddict():
    # TypedDict 实例化不报错，关键字段存在于 __annotations__
    annotations = AnalysisState.__annotations__
    required_fields = [
        "task", "target_brand", "competitor_brands", "conversation_id", "run_id",
        "raw_reviews", "total_review_count", "dimensions", "dimension_coverage",
        "dimension_scores", "target_weaknesses", "competitor_advantages",
        "content_gaps", "has_interception_opportunity",
        "interception_suggestions", "report_markdown", "final_output",
    ]
    for field in required_fields:
        assert field in annotations, f"Missing field: {field}"


def test_dimension_discovery_prompt_loaded():
    prompt = get_system_prompt("dimension_discovery")
    assert len(prompt) > 20
    assert "维度" in prompt or "dimension" in prompt.lower()


def test_gap_analysis_prompt_loaded():
    prompt = get_system_prompt("gap_analysis")
    assert len(prompt) > 20
    assert "has_interception_opportunity" in prompt


def test_interception_prompt_loaded():
    prompt = get_system_prompt("interception")
    assert len(prompt) > 20
    assert "evidence_quotes" in prompt

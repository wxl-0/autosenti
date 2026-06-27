from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task: str
    user_id: str
    project_id: int
    conversation_id: str
    run_id: int
    messages: list[dict[str, str]]
    conversation_summary: str
    current_focus: str
    uploaded_file_id: int | None
    selected_cluster_id: int | None
    selected_opportunity_id: int | None
    retrieved_feedback: list[dict[str, Any]]
    evidence_summary: dict[str, Any]
    metric_summary: str
    agent_steps: list[dict[str, Any]]
    step_summaries: list[str]
    draft_prd: str
    current_prd_id: int
    reviewer_result: dict[str, Any]
    needs_human_review: bool
    final_output: str


class AnalysisState(TypedDict, total=False):
    task: str
    target_brand: str
    competitor_brands: list[str]
    conversation_id: str
    run_id: int

    # 爬虫输出
    raw_reviews: dict           # brand → list[{text, rating, date, url, brand}]
    total_review_count: int

    # 维度发现
    dimensions: list[str]       # LLM 自动发现，非固定
    dimension_coverage: dict    # dimension → count（ReAct 判断依据）

    # 情绪分析
    dimension_scores: dict      # brand → dimension → {pos_rate, neg_rate, count, top_quotes}

    # 缺口检测
    target_weaknesses: list[dict]
    competitor_advantages: list[dict]
    content_gaps: list[dict]
    has_interception_opportunity: bool  # 条件路由开关

    # 拦截策略
    interception_suggestions: list[dict]

    # 输出
    report_markdown: str
    final_output: str

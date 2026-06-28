from typing import Any, TypedDict


class AnalysisState(TypedDict, total=False):
    task: str
    target_brand: str
    competitor_brands: list[str]
    conversation_id: str
    run_id: int

    # 爬虫输出
    raw_reviews: dict           # brand → list[{text, rating, date, brand}]
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

    # LLM 分析输出（丰富报告用）
    executive_summary: str
    our_strengths: list[dict]       # [{dimension, score_gap, top_competitor, content_angle}]
    our_gaps: list[dict]            # [{dimension, competitor, score_gap, response_angle}]
    competitor_profiles: list[dict] # [{brand, top_strengths, top_weakness, user_perception}]

    # 输出
    report_markdown: str
    final_output: str

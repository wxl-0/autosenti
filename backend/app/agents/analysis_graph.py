import json
from datetime import datetime
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.state import AnalysisState
from app.core.llm import call_llm
from app.db.models import AgentRun, SentimentAlert
from app.services.observability_service import agent_step
from app.services.scraper_service import scrape_all_brands, scrape_pages_for_brand, CAR_ID_MAP


def _count_dimension_mentions(dimension: str, reviews: list[dict]) -> int:
    kw = dimension.replace("体验", "").replace("系统", "").replace("性能", "")
    return sum(1 for r in reviews if kw in r.get("text", ""))


def _compute_dimension_scores(reviews_by_brand: dict, dimensions: list[str]) -> dict:
    scores = {}
    for brand, reviews in reviews_by_brand.items():
        scores[brand] = {}
        for dim in dimensions:
            kw = dim.replace("体验", "").replace("系统", "").replace("性能", "")
            relevant = [r for r in reviews if kw in r.get("text", "")]
            if not relevant:
                scores[brand][dim] = {"pos_rate": 0, "neg_rate": 0, "count": 0, "top_quotes": []}
                continue
            pos_words = ["好", "棒", "满意", "宽敞", "流畅", "快", "稳定", "喜欢"]
            neg_words = ["差", "卡", "慢", "差劲", "失望", "噪", "不好", "问题"]
            pos = sum(1 for r in relevant if any(w in r["text"] for w in pos_words))
            neg = sum(1 for r in relevant if any(w in r["text"] for w in neg_words))
            total = len(relevant)
            scores[brand][dim] = {
                "pos_rate": round(pos / total, 2),
                "neg_rate": round(neg / total, 2),
                "count": total,
                "top_quotes": [r["text"][:100] for r in relevant[:3]],
            }
    return scores


async def run_analysis_workflow(
    db: Session,
    target_brand: str,
    competitor_brands: list[str],
    max_pages: int = 3,
    conversation_id: str | None = None,
) -> AnalysisState:
    run = AgentRun(
        conversation_id=conversation_id,
        user_task=f"竞品分析：{target_brand} vs {', '.join(competitor_brands)}",
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    all_brands = [target_brand] + competitor_brands
    brand_car_id_map = {b: CAR_ID_MAP.get(b, "0") for b in all_brands}

    async def orchestrator(state: AnalysisState) -> AnalysisState:
        with agent_step(db, run.id, "Orchestrator", "parse_brands", input_data={"brands": all_brands}) as out:
            out["step_summary"] = f"分析目标：{target_brand}；竞品：{', '.join(competitor_brands)}"
        return {**state, "target_brand": target_brand, "competitor_brands": competitor_brands}

    async def scraper(state: AnalysisState) -> AnalysisState:
        with agent_step(db, run.id, "Scraper", "scrape_reviews", "autohome_scraper") as out:
            raw = scrape_all_brands(brand_car_id_map, max_pages=max_pages)
            total = sum(len(v) for v in raw.values())
            out["step_summary"] = f"抓取 {len(raw)} 个品牌，共 {total} 条评论"
        return {**state, "raw_reviews": raw, "total_review_count": total}

    async def dimension_discoverer(state: AnalysisState) -> AnalysisState:
        raw = state["raw_reviews"]
        # 取各品牌前 30 条送 LLM
        sample_texts = []
        for brand, reviews in raw.items():
            for r in reviews[:30]:
                sample_texts.append(f"[{brand}] {r['text'][:200]}")

        with agent_step(db, run.id, "DimensionDiscoverer", "discover_dimensions", "llm") as out:
            result = await call_llm(db, "dimension_discoverer", "dimension_discovery",
                                    {"reviews": sample_texts}, run_id=run.id)
            dims = result.get("dimensions", ["空间体验", "车机系统", "续航里程", "驾驶感受", "外观设计"])
            out["step_summary"] = f"发现 {len(dims)} 个维度：{', '.join(dims)}"

        # 局部 ReAct：维度覆盖不足时追加抓取
        target_reviews = raw.get(target_brand, [])
        coverage = {dim: _count_dimension_mentions(dim, target_reviews) for dim in dims}
        for dim, cnt in coverage.items():
            if cnt < 8:
                with agent_step(db, run.id, "DimensionDiscoverer", f"react_fetch_{dim}", "autohome_scraper") as out:
                    extra = scrape_pages_for_brand(target_brand, brand_car_id_map[target_brand], pages=[4, 5])
                    raw[target_brand] = raw.get(target_brand, []) + extra
                    new_cnt = _count_dimension_mentions(dim, raw[target_brand])
                    out["step_summary"] = f"维度「{dim}」覆盖不足（{cnt} 条），追加抓取第 4-5 页，新增 {len(extra)} 条，当前覆盖 {new_cnt} 条"

        coverage_updated = {dim: _count_dimension_mentions(dim, raw[target_brand]) for dim in dims}
        return {**state, "dimensions": dims, "dimension_coverage": coverage_updated, "raw_reviews": raw}

    async def sentiment_analyzer(state: AnalysisState) -> AnalysisState:
        with agent_step(db, run.id, "SentimentAnalyzer", "compute_scores") as out:
            scores = _compute_dimension_scores(state["raw_reviews"], state["dimensions"])
            out["step_summary"] = f"计算 {len(scores)} 个品牌 × {len(state['dimensions'])} 个维度的情绪评分矩阵"
        return {**state, "dimension_scores": scores}

    async def gap_detector(state: AnalysisState) -> AnalysisState:
        with agent_step(db, run.id, "GapDetector", "detect_gaps", "llm") as out:
            result = await call_llm(db, "gap_detector", "gap_analysis",
                                    {"dimension_scores": state["dimension_scores"],
                                     "target_brand": state["target_brand"]}, run_id=run.id)
            has_opp = bool(result.get("has_interception_opportunity", False))
            out["step_summary"] = f"发现拦截机会：{'是' if has_opp else '否'}"
        return {
            **state,
            "target_weaknesses": result.get("target_weaknesses", []),
            "competitor_advantages": result.get("competitor_advantages", []),
            "content_gaps": result.get("content_gaps", []),
            "has_interception_opportunity": has_opp,
        }

    def route_after_gap(state: AnalysisState) -> str:
        return "interception_planner" if state.get("has_interception_opportunity") else "report_compiler"

    async def interception_planner(state: AnalysisState) -> AnalysisState:
        # 从 raw_reviews 中提取真实引用（ContextBuilder 注入，禁止 LLM 编造）
        raw = state["raw_reviews"]
        target_quotes = [r["text"][:150] for r in raw.get(state["target_brand"], [])[:20]]
        competitor_quotes: dict[str, list[str]] = {}
        for comp in state["competitor_brands"]:
            competitor_quotes[comp] = [r["text"][:150] for r in raw.get(comp, [])[:20]]

        with agent_step(db, run.id, "InterceptionPlanner", "generate_interceptions", "llm") as out:
            result = await call_llm(
                db, "interception_planner", "interception",
                {
                    "target_brand": state["target_brand"],
                    "competitor_advantages": state["competitor_advantages"],
                    "target_weaknesses": state["target_weaknesses"],
                    "dimension_scores": state["dimension_scores"],
                    "raw_quotes": {"target": target_quotes, "competitors": competitor_quotes},
                },
                run_id=run.id,
            )
            suggestions = result if isinstance(result, list) else result.get("suggestions", [])
            # 写入数据库
            for i, s in enumerate(suggestions):
                db.add(SentimentAlert(
                    conversation_id=conversation_id,
                    target_brand=state["target_brand"],
                    competitor_brand=s.get("competitor", ""),
                    dimension=s.get("dimension", ""),
                    gap_type="competitor_advantage",
                    severity=s.get("priority", "medium"),
                    interception_angle=s.get("interception_angle", ""),
                    evidence_quotes=json.dumps(s.get("evidence_quotes", []), ensure_ascii=False),
                    content_format=s.get("content_format", ""),
                    priority_rank=i + 1,
                ))
            db.commit()
            out["step_summary"] = f"生成 {len(suggestions)} 条拦截策略，已写入 SentimentAlert 表"
        return {**state, "interception_suggestions": suggestions}

    async def report_compiler(state: AnalysisState) -> AnalysisState:
        with agent_step(db, run.id, "ReportCompiler", "compile_report") as out:
            lines = [f"# {state.get('target_brand', '')} 竞品维度分析报告\n"]
            lines.append("## 一、内容缺口诊断\n")
            gaps = state.get("content_gaps", [])
            if gaps:
                lines.append("| 维度 | 评论量 |\n|------|------|\n")
                for g in gaps:
                    lines.append(f"| {g.get('dimension')} | {g.get('count')} |\n")
            else:
                lines.append("暂未发现明显内容缺口。\n")

            lines.append("\n## 二、竞品拦截策略\n")
            suggestions = state.get("interception_suggestions", [])
            if suggestions:
                lines.append("| 维度 | 竞品 | 拦截角度 | 内容形式 | 优先级 |\n|------|------|---------|---------|------|\n")
                for s in suggestions:
                    lines.append(f"| {s.get('dimension','')} | {s.get('competitor','')} | {s.get('interception_angle','')} | {s.get('content_format','')} | {s.get('priority','')} |\n")
            else:
                lines.append("未发现明显拦截机会。\n")

            lines.append("\n## 三、观望用户核心疑虑\n")
            weaknesses = state.get("target_weaknesses", [])
            for w in weaknesses:
                lines.append(f"- {w.get('dimension')}：负面率 {round(w.get('neg_rate', 0) * 100)}%\n")

            lines.append("\n## 四、执行优先级 TOP5\n")
            top5 = suggestions[:5] if suggestions else []
            for i, s in enumerate(top5, 1):
                quotes = s.get("evidence_quotes", [])
                quote_str = f"（用户原话：「{quotes[0]}」）" if quotes else ""
                lines.append(f"{i}. **{s.get('dimension')}** — {s.get('interception_angle')} {quote_str}\n")

            md = "".join(lines)
            final = f"分析完成。发现 {len(state.get('dimensions', []))} 个维度，{'有' if state.get('has_interception_opportunity') else '无'}拦截机会，生成了 {len(suggestions)} 条策略。"
            out["step_summary"] = "Markdown 报告已生成"
        run.status = "success"
        run.final_output = final
        run.report_markdown = md
        run.finished_at = datetime.utcnow()
        db.commit()
        return {**state, "report_markdown": md, "final_output": final}

    graph = StateGraph(AnalysisState)
    for name, fn in [
        ("orchestrator", orchestrator),
        ("scraper", scraper),
        ("dimension_discoverer", dimension_discoverer),
        ("sentiment_analyzer", sentiment_analyzer),
        ("gap_detector", gap_detector),
        ("interception_planner", interception_planner),
        ("report_compiler", report_compiler),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "orchestrator")
    graph.add_edge("orchestrator", "scraper")
    graph.add_edge("scraper", "dimension_discoverer")
    graph.add_edge("dimension_discoverer", "sentiment_analyzer")
    graph.add_edge("sentiment_analyzer", "gap_detector")
    graph.add_conditional_edges(
        "gap_detector",
        route_after_gap,
        {"interception_planner": "interception_planner", "report_compiler": "report_compiler"},
    )
    graph.add_edge("interception_planner", "report_compiler")
    graph.add_edge("report_compiler", END)

    initial: AnalysisState = {
        "task": f"竞品分析：{target_brand}",
        "target_brand": target_brand,
        "competitor_brands": competitor_brands,
        "conversation_id": conversation_id or "",
        "run_id": run.id,
    }
    app = graph.compile()
    try:
        state = await app.ainvoke(initial)
        return state
    except Exception as exc:
        run.status = "failed"
        run.final_output = str(exc)
        run.finished_at = datetime.utcnow()
        db.commit()
        raise

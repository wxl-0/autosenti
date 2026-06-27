import json
from datetime import datetime
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.state import AnalysisState
from app.core.llm import call_llm
from app.db.models import AgentRun, SentimentAlert
from app.services.observability_service import agent_step
from app.services.scraper_service import scrape_all_brands, scrape_pages_for_brand, CAR_ID_MAP


# 汽车之家 scoreList 标准维度（API 直接提供，无需 LLM 发现）
STANDARD_DIMENSIONS = ["空间", "驾驶感受", "续航", "外观", "内饰", "性价比", "智能化"]


def _count_dimension_mentions(dimension: str, reviews: list[dict]) -> int:
    """统计有 scoreList 评分记录的条数（替代文本关键词匹配）。"""
    return sum(1 for r in reviews if dimension in r.get("scores", {}))


def _compute_dimension_scores(reviews_by_brand: dict, dimensions: list[str]) -> dict:
    """基于 API scoreList 结构化评分计算各品牌×维度得分矩阵。

    每条 review 的 scores 字段格式：{"空间": 5, "续航": 4, ...}（1-5 分）
    pos: 评分 >= 4；neg: 评分 <= 2
    """
    scores = {}
    for brand, reviews in reviews_by_brand.items():
        scores[brand] = {}
        for dim in dimensions:
            dim_scores = [r["scores"][dim] for r in reviews if dim in r.get("scores", {})]
            if not dim_scores:
                scores[brand][dim] = {"avg_score": 0, "pos_rate": 0, "neg_rate": 0, "count": 0, "top_quotes": []}
                continue
            total = len(dim_scores)
            pos = sum(1 for s in dim_scores if s >= 4)
            neg = sum(1 for s in dim_scores if s <= 2)
            avg = round(sum(dim_scores) / total, 2)
            top_quotes = [r["text"][:100] for r in reviews if dim in r.get("scores", {})][:3]
            scores[brand][dim] = {
                "avg_score": avg,
                "pos_rate": round(pos / total, 2),
                "neg_rate": round(neg / total, 2),
                "count": total,
                "top_quotes": top_quotes,
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
        # 使用 API scoreList 标准维度，无需 LLM 发现
        dims = STANDARD_DIMENSIONS

        # ReAct：覆盖不足时追加抓取
        target_reviews = raw.get(target_brand, [])
        coverage = {dim: _count_dimension_mentions(dim, target_reviews) for dim in dims}
        with agent_step(db, run.id, "DimensionDiscoverer", "check_coverage") as out:
            low_dims = [d for d, c in coverage.items() if c < 8]
            if low_dims:
                extra = scrape_pages_for_brand(target_brand, brand_car_id_map[target_brand], pages=[4, 5])
                raw[target_brand] = raw.get(target_brand, []) + extra
                coverage = {dim: _count_dimension_mentions(dim, raw[target_brand]) for dim in dims}
            out["step_summary"] = f"维度：{', '.join(dims)}；覆盖分布：{coverage}"

        return {**state, "dimensions": dims, "dimension_coverage": coverage, "raw_reviews": raw}

    async def sentiment_analyzer(state: AnalysisState) -> AnalysisState:
        with agent_step(db, run.id, "SentimentAnalyzer", "compute_scores") as out:
            scores = _compute_dimension_scores(state["raw_reviews"], state["dimensions"])
            out["step_summary"] = f"计算 {len(scores)} 个品牌 × {len(state['dimensions'])} 个维度的情绪评分矩阵"
        return {**state, "dimension_scores": scores}

    async def gap_detector(state: AnalysisState) -> AnalysisState:
        scores = state["dimension_scores"]
        target = state["target_brand"]

        # 先用数据计算出实际差距，再送 LLM 做策略解读
        target_scores = scores.get(target, {})
        computed_weaknesses = []
        computed_advantages = []
        computed_gaps = []

        for dim in state["dimensions"]:
            t_data = target_scores.get(dim, {})
            t_avg = t_data.get("avg_score", 0)
            t_count = t_data.get("count", 0)
            if t_count == 0:
                continue
            if t_data.get("neg_rate", 0) >= 0.2 or t_avg <= 3.5:
                computed_weaknesses.append({"dimension": dim, "avg_score": t_avg, "neg_rate": t_data.get("neg_rate", 0), "count": t_count})
            for comp in state["competitor_brands"]:
                c_data = scores.get(comp, {}).get(dim, {})
                c_avg = c_data.get("avg_score", 0)
                c_count = c_data.get("count", 0)
                if c_count == 0:
                    continue
                gap = round(c_avg - t_avg, 2)
                if gap >= 0.3:
                    computed_advantages.append({"competitor": comp, "dimension": dim, "gap": gap, "competitor_avg": c_avg, "target_avg": t_avg})
                if t_count < 5:
                    computed_gaps.append({"dimension": dim, "count": t_count})

        has_opp = bool(computed_weaknesses or computed_advantages)

        with agent_step(db, run.id, "GapDetector", "detect_gaps", "llm") as out:
            result = await call_llm(db, "gap_detector", "gap_analysis",
                                    {"dimension_scores": scores,
                                     "target_brand": target,
                                     "computed_weaknesses": computed_weaknesses,
                                     "computed_competitor_advantages": computed_advantages}, run_id=run.id)
            # LLM 结果优先，但如果数据已经发现差距则保底开启拦截流程
            llm_weaknesses = result.get("target_weaknesses") or computed_weaknesses
            llm_advantages = result.get("competitor_advantages") or computed_advantages
            llm_gaps = result.get("content_gaps") or computed_gaps
            llm_has_opp = bool(result.get("has_interception_opportunity", has_opp))
            out["step_summary"] = f"发现拦截机会：{'是' if llm_has_opp else '否'}，弱项 {len(llm_weaknesses)} 个，竞品优势 {len(llm_advantages)} 个"

        return {
            **state,
            "target_weaknesses": llm_weaknesses,
            "competitor_advantages": llm_advantages,
            "content_gaps": llm_gaps,
            "has_interception_opportunity": llm_has_opp,
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

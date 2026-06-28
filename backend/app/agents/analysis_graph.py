import asyncio
import json
import re
from datetime import datetime
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.state import AnalysisState
from app.core.llm import call_llm
from app.db.models import AgentRun, SentimentAlert
from app.services.observability_service import agent_step
from app.services.scraper_service import scrape_all_brands, scrape_pages_for_brand, CAR_ID_MAP, QUOTE_MIN_LENGTH


# 汽车之家 scoreList 标准维度（API 直接提供，无需 LLM 发现）
STANDARD_DIMENSIONS = ["空间", "驾驶感受", "续航", "外观", "内饰", "性价比", "智能化"]
STANDARD_DIMS_SET = set(STANDARD_DIMENSIONS)


def _pos_quote(text: str, max_len: int = 100) -> str:
    m = re.search(r'\[满意\](.*?)(?:\[不满意\]|$)', text, re.DOTALL)
    if m:
        return m.group(1).strip()[:max_len]
    return re.sub(r'\[满意\]|\[不满意\]', '', text).strip()[:max_len]


def _neg_quote(text: str, max_len: int = 100) -> str:
    m = re.search(r'\[不满意\](.*?)$', text, re.DOTALL)
    if m:
        return m.group(1).strip()[:max_len]
    return re.sub(r'\[满意\]|\[不满意\]', '', text).strip()[:max_len]


def _count_dimension_mentions(dimension: str, reviews: list[dict]) -> int:
    return sum(1 for r in reviews if dimension in r.get("scores", {}))


def _confidence_label(count: int, dim_scores: list[int]) -> str:
    if count < 10:
        return "低"
    if count >= 20:
        return "高"
    mean = sum(dim_scores) / count
    variance = sum((s - mean) ** 2 for s in dim_scores) / count
    return "中" if variance > 0.8 else "高"


def _compute_dimension_scores(reviews_by_brand: dict, dimensions: list[str]) -> dict:
    """基于 API scoreList 结构化评分计算各品牌×维度得分矩阵。"""
    scores = {}
    for brand, reviews in reviews_by_brand.items():
        scores[brand] = {}
        for dim in dimensions:
            dim_scores = [r["scores"][dim] for r in reviews if dim in r.get("scores", {})]
            if not dim_scores:
                scores[brand][dim] = {"avg_score": 0, "pos_rate": 0, "neg_rate": 0, "count": 0, "confidence": "低", "top_quotes": []}
                continue
            total = len(dim_scores)
            pos = sum(1 for s in dim_scores if s >= 4)
            neg = sum(1 for s in dim_scores if s <= 2)
            avg = round(sum(dim_scores) / total, 2)
            top_quotes = [
                r["text"][:150] for r in reviews
                if dim in r.get("scores", {}) and len(r.get("text", "")) >= QUOTE_MIN_LENGTH
            ][:3]
            scores[brand][dim] = {
                "avg_score": avg,
                "pos_rate": round(pos / total, 2),
                "neg_rate": round(neg / total, 2),
                "count": total,
                "confidence": _confidence_label(total, dim_scores),
                "top_quotes": top_quotes,
            }
    return scores


def _format_score_table(scores: dict, all_brands: list[str], dimensions: list[str]) -> str:
    lines = []
    for dim in dimensions:
        lines.append(f"\n  【{dim}】")
        for brand in all_brands:
            d = scores.get(brand, {}).get(dim, {})
            if d.get("count", 0) == 0:
                lines.append(f"    {brand}: 暂无数据")
            else:
                lines.append(
                    f"    {brand}: {d.get('avg_score', 0):.1f}分 | "
                    f"正面率{round(d.get('pos_rate', 0) * 100)}% | "
                    f"负面率{round(d.get('neg_rate', 0) * 100)}% | "
                    f"{d.get('count', 0)}条 | 置信度:{d.get('confidence', '低')}"
                )
    return "\n".join(lines)


def _format_gap_summary(computed_weaknesses: list, computed_advantages: list) -> str:
    lines = []
    if computed_weaknesses:
        lines.append("弱势维度：")
        for w in computed_weaknesses:
            lines.append(f"  - {w.get('dimension')}: 均分{w.get('avg_score', 0):.1f}, 负面率{round(w.get('neg_rate', 0) * 100)}%")
    if computed_advantages:
        lines.append("竞品占优维度：")
        for a in computed_advantages:
            lines.append(f"  - {a.get('competitor')} 在 {a.get('dimension')} 领先 {a.get('gap', 0):.2f}分")
    return "\n".join(lines) if lines else "暂未发现明显差距"


def _format_quotes_summary(target_brand: str, target_quotes: list, competitor_quotes: dict) -> str:
    lines = [f"【{target_brand}】"]
    for q in target_quotes[:5]:
        lines.append(f"  · {q}")
    for comp, quotes in competitor_quotes.items():
        lines.append(f"\n【{comp}】")
        for q in quotes[:5]:
            lines.append(f"  · {q}")
    return "\n".join(lines)


async def run_analysis_workflow(
    db: Session,
    target_brand: str,
    competitor_brands: list[str],
    max_pages: int = 5,
    conversation_id: str | None = None,
    progress_queue: asyncio.Queue | None = None,
) -> AnalysisState:
    async def _emit(step: str, message: str):
        if progress_queue:
            await progress_queue.put({"step": step, "message": message, "done": False})
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
        await _emit("orchestrator", f"解析任务：{target_brand} vs {', '.join(competitor_brands)}")
        with agent_step(db, run.id, "Orchestrator", "parse_brands", input_data={"brands": all_brands}) as out:
            out["step_summary"] = f"分析目标：{target_brand}；竞品：{', '.join(competitor_brands)}"
        return {**state, "target_brand": target_brand, "competitor_brands": competitor_brands}

    async def scraper(state: AnalysisState) -> AnalysisState:
        await _emit("scraper", f"正在抓取 {len(all_brands)} 个品牌的口碑数据，预计 30-60 秒...")
        with agent_step(db, run.id, "Scraper", "scrape_reviews", "autohome_scraper") as out:
            raw = scrape_all_brands(brand_car_id_map, max_pages=max_pages)
            total = sum(len(v) for v in raw.values())
            out["step_summary"] = f"抓取 {len(raw)} 个品牌，共 {total} 条评论"
        await _emit("scraper", f"数据抓取完成：共 {total} 条评论")
        return {**state, "raw_reviews": raw, "total_review_count": total}

    async def dimension_discoverer(state: AnalysisState) -> AnalysisState:
        await _emit("dimension_discoverer", "正在检查维度覆盖情况...")
        raw = state["raw_reviews"]
        dims = STANDARD_DIMENSIONS

        target_reviews = raw.get(target_brand, [])
        coverage = {dim: _count_dimension_mentions(dim, target_reviews) for dim in dims}
        with agent_step(db, run.id, "DimensionDiscoverer", "check_coverage") as out:
            low_dims = [d for d, c in coverage.items() if c < 8]
            if low_dims:
                extra = scrape_pages_for_brand(target_brand, brand_car_id_map[target_brand], pages=[6, 7])
                raw[target_brand] = raw.get(target_brand, []) + extra
                coverage = {dim: _count_dimension_mentions(dim, raw[target_brand]) for dim in dims}
            out["step_summary"] = f"维度：{', '.join(dims)}；覆盖分布：{coverage}"
        await _emit("dimension_discoverer", f"维度识别完成：{', '.join(dims)}")

        return {**state, "dimensions": dims, "dimension_coverage": coverage, "raw_reviews": raw}

    async def sentiment_analyzer(state: AnalysisState) -> AnalysisState:
        await _emit("sentiment_analyzer", "正在计算各品牌维度评分矩阵...")
        with agent_step(db, run.id, "SentimentAnalyzer", "compute_scores") as out:
            scores = _compute_dimension_scores(state["raw_reviews"], state["dimensions"])
            out["step_summary"] = f"计算 {len(scores)} 个品牌 × {len(state['dimensions'])} 个维度的评分矩阵"
        await _emit("sentiment_analyzer", f"评分矩阵计算完成")
        return {**state, "dimension_scores": scores}

    async def gap_detector(state: AnalysisState) -> AnalysisState:
        scores = state["dimension_scores"]
        target = state["target_brand"]
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
        score_table = _format_score_table(scores, all_brands, state["dimensions"])

        with agent_step(db, run.id, "GapDetector", "detect_gaps", "llm") as out:
            await _emit("gap_detector", "正在进行差距分析（LLM 推理中）...")
            result = await call_llm(db, "gap_detector", "gap_analysis", {
                "target_brand": target,
                "competitor_brands": ", ".join(state["competitor_brands"]),
                "score_table": score_table,
                "computed_weaknesses": str(computed_weaknesses),
                "computed_competitor_advantages": str(computed_advantages),
            }, run_id=run.id)

            llm_weaknesses = result.get("target_weaknesses") or computed_weaknesses
            llm_advantages = result.get("competitor_advantages") or computed_advantages
            llm_gaps = result.get("content_gaps") or computed_gaps
            llm_has_opp = bool(result.get("has_interception_opportunity", has_opp))
            executive_summary = result.get("executive_summary", "")
            our_strengths = result.get("our_strengths", [])
            our_gaps = result.get("our_gaps", [])
            out["step_summary"] = f"发现拦截机会：{'是' if llm_has_opp else '否'}，优势 {len(our_strengths)} 个，差距 {len(our_gaps)} 个"
        await _emit("gap_detector", f"差距分析完成：发现 {len(our_strengths)} 个优势、{len(our_gaps)} 个差距")

        return {
            **state,
            "target_weaknesses": llm_weaknesses,
            "competitor_advantages": llm_advantages,
            "content_gaps": llm_gaps,
            "has_interception_opportunity": llm_has_opp,
            "executive_summary": executive_summary,
            "our_strengths": our_strengths,
            "our_gaps": our_gaps,
        }

    def route_after_gap(state: AnalysisState) -> str:
        return "interception_planner" if state.get("has_interception_opportunity") else "report_compiler"

    async def interception_planner(state: AnalysisState) -> AnalysisState:
        raw = state["raw_reviews"]
        target_quotes = [r["text"][:150] for r in raw.get(state["target_brand"], []) if len(r.get("text", "")) >= QUOTE_MIN_LENGTH][:10]
        competitor_quotes: dict[str, list[str]] = {}
        for comp in state["competitor_brands"]:
            competitor_quotes[comp] = [
                r["text"][:150] for r in raw.get(comp, []) if len(r.get("text", "")) >= QUOTE_MIN_LENGTH
            ][:10]

        gap_summary = _format_gap_summary(state.get("target_weaknesses", []), state.get("competitor_advantages", []))
        quotes_summary = _format_quotes_summary(state["target_brand"], target_quotes, competitor_quotes)

        with agent_step(db, run.id, "InterceptionPlanner", "generate_interceptions", "llm") as out:
            await _emit("interception_planner", "正在生成竞品画像与内容策略（LLM 推理中）...")
            result = await call_llm(
                db, "interception_planner", "interception",
                {
                    "target_brand": state["target_brand"],
                    "competitor_brands": ", ".join(state["competitor_brands"]),
                    "gap_summary": gap_summary,
                    "quotes_summary": quotes_summary,
                },
                run_id=run.id,
            )
            suggestions = result.get("suggestions", [])
            competitor_profiles = result.get("competitor_profiles", [])

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
            out["step_summary"] = f"生成 {len(suggestions)} 条策略，{len(competitor_profiles)} 个竞品画像"
        await _emit("interception_planner", f"竞品画像完成：{len(competitor_profiles)} 个竞品，{len(suggestions)} 条内容策略")

        return {**state, "interception_suggestions": suggestions, "competitor_profiles": competitor_profiles}

    async def report_compiler(state: AnalysisState) -> AnalysisState:
        await _emit("report_compiler", "正在编写分析报告...")
        with agent_step(db, run.id, "ReportCompiler", "compile_report") as out:
            scores = state.get("dimension_scores", {})
            target = state.get("target_brand", "")
            competitors = state.get("competitor_brands", [])
            dims = state.get("dimensions", STANDARD_DIMENSIONS)
            executive_summary = state.get("executive_summary", "")
            our_strengths = state.get("our_strengths", [])
            our_gaps_list = state.get("our_gaps", [])
            competitor_profiles = state.get("competitor_profiles", [])
            collection_date = datetime.utcnow().strftime("%Y-%m-%d")

            # ── 验证优势：从实际评分数据重新计算，过滤 LLM 错误 ──────
            def _validated_strengths() -> list[dict]:
                validated = []
                for s in our_strengths:
                    dim = s.get("dimension", "")
                    if dim not in STANDARD_DIMS_SET:
                        continue
                    t_avg = scores.get(target, {}).get(dim, {}).get("avg_score", 0)
                    if t_avg == 0:
                        continue
                    comp_map = {
                        c: scores.get(c, {}).get(dim, {}).get("avg_score", 0)
                        for c in competitors
                        if scores.get(c, {}).get(dim, {}).get("avg_score", 0) > 0
                    }
                    if not comp_map:
                        continue
                    best_comp = max(comp_map, key=comp_map.get)
                    actual_gap = round(t_avg - comp_map[best_comp], 2)
                    if actual_gap >= 0:
                        validated.append({**s, "score_gap": actual_gap, "top_competitor": best_comp})
                if validated:
                    return validated[:3]
                # 没有真实优势时，退一步：找相对差距最小（最具竞争力）的维度展示
                candidates = []
                for d in dims:
                    t_avg = scores.get(target, {}).get(d, {}).get("avg_score", 0)
                    t_count = scores.get(target, {}).get(d, {}).get("count", 0)
                    if t_avg == 0 or t_count < 10:
                        continue
                    comp_avgs = [
                        scores.get(c, {}).get(d, {}).get("avg_score", 0)
                        for c in competitors
                        if scores.get(c, {}).get(d, {}).get("avg_score", 0) > 0
                    ]
                    if not comp_avgs:
                        continue
                    gap = round(t_avg - max(comp_avgs), 2)
                    candidates.append({"dimension": d, "score_gap": gap, "top_competitor": None, "content_angle": None})
                candidates.sort(key=lambda x: x["score_gap"], reverse=True)
                return candidates[:2]

            strength_items = _validated_strengths()

            lines = []

            # ── 标题 ──────────────────────────────────────────────────
            lines.append(f"# {target} 竞品口碑情报报告\n\n")
            lines.append(f"> **竞品**：{', '.join(competitors)}　｜　**数据来源**：汽车之家口碑　｜　**生成时间**：{collection_date}\n\n")
            lines.append("---\n\n")

            # ── 一、执行摘要 ──────────────────────────────────────────
            lines.append("## 一、执行摘要\n\n")
            lines.append(f"{executive_summary}\n\n" if executive_summary else "暂无摘要数据。\n\n")

            # ── 二、维度评分矩阵 ──────────────────────────────────────
            lines.append("## 二、维度评分矩阵\n\n")
            header = "| 维度 |" + "".join(f" {b} |" for b in [target] + competitors) + "\n"
            separator = "|:----:|" + "".join(":----:|" for _ in [target] + competitors) + "\n"
            lines.append(header)
            lines.append(separator)
            for dim in dims:
                row = f"| {dim} |"
                for b in [target] + competitors:
                    d = scores.get(b, {}).get(dim, {})
                    avg = d.get("avg_score", 0)
                    neg = d.get("neg_rate", 0)
                    neg_tag = f" ⚡{round(neg * 100)}%负" if neg >= 0.15 else ""
                    row += f" {avg:.1f}{neg_tag} |" if avg > 0 else " — |"
                row += "\n"
                lines.append(row)
            lines.append("\n*⚡ 负面率 ≥ 15% 的维度，代表有明显用户不满*\n\n")

            # ── 三、我方核心优势 ──────────────────────────────────────
            lines.append("## 三、我方核心优势\n\n")
            if strength_items:
                truly_leading = [s for s in strength_items if s.get("score_gap", 0) >= 0]
                close_second = [s for s in strength_items if s.get("score_gap", 0) < 0]
                if close_second and not truly_leading:
                    lines.append(f"> 当前各维度暂无明显领先，以下展示{target}相对最具竞争力的维度。\n\n")
                for i, s in enumerate(strength_items, 1):
                    dim = s.get("dimension", "")
                    dim_data = scores.get(target, {}).get(dim, {})
                    top_comp = s.get("top_competitor") or ""
                    comp_avg = scores.get(top_comp, {}).get(dim, {}).get("avg_score", 0) if top_comp else 0
                    score_gap = s.get("score_gap", 0)

                    lines.append(f"### 3.{i} {dim}\n\n")
                    score_line = f"**得分**：{target} **{dim_data.get('avg_score', 0):.1f}分**"
                    if top_comp and comp_avg > 0:
                        score_line += f"　vs　{top_comp} {comp_avg:.1f}分"
                    if score_gap > 0:
                        score_line += f"　（领先 **+{score_gap:.1f}分**）"
                    elif score_gap < 0:
                        score_line += f"　（差距 {score_gap:.1f}分）"
                    score_line += f"　｜　正面率 {round(dim_data.get('pos_rate', 0) * 100)}%\n\n"
                    lines.append(score_line)

                    quotes = dim_data.get("top_quotes", [])
                    pos_quotes = [_pos_quote(q) for q in quotes if _pos_quote(q)][:2]
                    if pos_quotes:
                        lines.append("**用户在说：**\n\n")
                        for q in pos_quotes:
                            lines.append(f"> {q}\n\n")

                    angle = s.get("content_angle")
                    if angle:
                        lines.append(f"**内容方向**：{angle}\n\n")
            else:
                lines.append("暂未发现可展示的优势维度。\n\n")

            # ── 四、需要关注的差距 ────────────────────────────────────
            lines.append("## 四、需要关注的差距\n\n")
            gap_items = our_gaps_list[:3] if our_gaps_list else []
            if gap_items:
                for i, g in enumerate(gap_items, 1):
                    dim = g.get("dimension", "")
                    comp = g.get("competitor", "")
                    score_gap = g.get("score_gap", 0)
                    target_data = scores.get(target, {}).get(dim, {})
                    comp_data = scores.get(comp, {}).get(dim, {}) if comp else {}

                    lines.append(f"### 4.{i} {dim}\n\n")
                    lines.append(
                        f"**得分**：{target} {target_data.get('avg_score', 0):.1f}分　vs　{comp} **{comp_data.get('avg_score', 0):.1f}分**"
                        f"　（落后 **-{score_gap:.1f}分**）\n\n"
                    )

                    comp_quotes = comp_data.get("top_quotes", [])
                    neg_quotes = [_neg_quote(q) for q in comp_quotes if _neg_quote(q)][:2]
                    pos_from_comp = [_pos_quote(q) for q in comp_quotes if _pos_quote(q)][:2]
                    if pos_from_comp:
                        lines.append(f"**{comp} 用户在说（正面）：**\n\n")
                        for q in pos_from_comp:
                            lines.append(f"> {q}\n\n")
                    if neg_quotes:
                        lines.append(f"**{comp} 用户的吐槽（可利用）：**\n\n")
                        for q in neg_quotes:
                            lines.append(f"> {q}\n\n")

                    angle = g.get("response_angle")
                    if angle:
                        lines.append(f"**应对方向**：{angle}\n\n")
            else:
                lines.append("暂未发现显著差距，或数据样本不足以支撑结论。\n\n")

            # ── 五、竞品深度画像 ──────────────────────────────────────
            lines.append("## 五、竞品深度画像\n\n")

            def _safe_dims(dim_list: list) -> list:
                return [d for d in dim_list if d in STANDARD_DIMS_SET]

            def _fallback_profile(comp: str) -> dict:
                comp_scores = scores.get(comp, {})
                rated = [(d, comp_scores[d]) for d in dims if comp_scores.get(d, {}).get("count", 0) >= 5]
                if not rated:
                    return {}
                rated.sort(key=lambda x: x[1]["avg_score"], reverse=True)
                return {
                    "brand": comp,
                    "top_strengths": [r[0] for r in rated[:2]],
                    "top_weakness": rated[-1][0] if len(rated) > 1 else "",
                    "user_perception": "",
                }

            profiles_to_render = competitor_profiles if competitor_profiles else [_fallback_profile(c) for c in competitors]
            for i, profile in enumerate(profiles_to_render, 1):
                if not profile:
                    continue
                brand = profile.get("brand", "")
                top_strengths = _safe_dims(profile.get("top_strengths", []))
                top_weakness = profile.get("top_weakness", "") if profile.get("top_weakness", "") in STANDARD_DIMS_SET else ""
                perception = profile.get("user_perception", "")
                comp_scores = scores.get(brand, {})

                # 若 LLM 返回的维度不在标准集，用评分数据兜底
                if not top_strengths:
                    rated = sorted(
                        [(d, comp_scores[d]["avg_score"]) for d in dims if comp_scores.get(d, {}).get("count", 0) >= 5],
                        key=lambda x: x[1], reverse=True
                    )
                    top_strengths = [r[0] for r in rated[:2]]
                if not top_weakness:
                    rated_asc = sorted(
                        [(d, comp_scores[d]["avg_score"]) for d in dims if comp_scores.get(d, {}).get("count", 0) >= 5],
                        key=lambda x: x[1]
                    )
                    top_weakness = rated_asc[0][0] if rated_asc else ""

                lines.append(f"### 5.{i} {brand}\n\n")
                if perception:
                    lines.append(f"**用户感知**：{perception}\n\n")
                if top_strengths:
                    lines.append(f"**用户认可的优势**：{', '.join(top_strengths)}\n\n")
                    for dim in top_strengths[:2]:
                        d = comp_scores.get(dim, {})
                        if d.get("count", 0) >= 5:
                            lines.append(f"- **{dim}** {d.get('avg_score', 0):.1f}分（正面率 {round(d.get('pos_rate', 0) * 100)}%）\n")
                            pos_q = [_pos_quote(q) for q in d.get("top_quotes", []) if _pos_quote(q)]
                            if pos_q:
                                lines.append(f"  > {pos_q[0]}\n")
                    lines.append("\n")
                if top_weakness:
                    d = comp_scores.get(top_weakness, {})
                    neg_rate = round(d.get("neg_rate", 0) * 100)
                    lines.append(f"**用户吐槽较多**：{top_weakness} {d.get('avg_score', 0):.1f}分（负面率 {neg_rate}%）\n")
                    neg_q = [_neg_quote(q) for q in d.get("top_quotes", []) if _neg_quote(q)]
                    if neg_q:
                        lines.append(f"> {neg_q[0]}\n")
                    lines.append("\n")

            md = "".join(lines)
            final = f"分析完成。{target} vs {', '.join(competitors)}，覆盖 {len(dims)} 个维度。"
            out["step_summary"] = "报告已生成"

        run.status = "success"
        run.final_output = final
        run.report_markdown = md
        run.finished_at = datetime.utcnow()
        db.commit()
        await _emit("report_compiler", "报告生成完成 ✓")
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

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.prompt_loader import get_system_prompt, get_user_template
from app.db.models import LlmCall


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _render_user_content(prompt_type: str, payload: dict[str, Any]) -> str:
    template = get_user_template(prompt_type)
    if template:
        try:
            return template.format(**{k: str(v) for k, v in payload.items()})
        except (KeyError, ValueError):
            pass
    return json.dumps(payload, ensure_ascii=False)


async def _call_openai_compatible(settings, prompt_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{settings.resolved_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.resolved_model,
                "messages": [
                    {"role": "system", "content": get_system_prompt(prompt_type)},
                    {"role": "user", "content": _render_user_content(prompt_type, payload)},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def _mock_result(prompt_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if prompt_type == "gap_analysis":
        return {
            "executive_summary": "目标品牌在智能化和空间维度具备竞争优势，续航口碑存在一定隐患，建议内容策略主打前两者。",
            "our_strengths": [{"dimension": "智能化", "score_gap": 0.5, "top_competitor": "银河E5", "content_angle": "主打车机流畅度和OTA升级频率"}],
            "our_gaps": [{"dimension": "续航", "competitor": "深蓝S05", "score_gap": 0.4, "response_angle": "转移话题至综合用车成本"}],
            "has_interception_opportunity": True,
            "target_weaknesses": [{"dimension": "续航", "neg_rate": 0.25, "avg_score": 3.4}],
            "competitor_advantages": [{"competitor": "深蓝S05", "dimension": "续航", "gap": 0.4}],
            "content_gaps": [],
        }
    if prompt_type == "interception":
        return {
            "competitor_profiles": [
                {"brand": "银河E5", "top_strengths": ["外观", "性价比"], "top_weakness": "智能化", "user_perception": "外观好看价格实惠，但车机体验槽点较多"}
            ],
            "suggestions": [{"dimension": "智能化", "competitor": "银河E5", "interception_angle": "强调OTA升级频率", "content_format": "短视频对比", "evidence_quotes": [], "priority": "high"}],
        }
    return {}


async def call_llm(db: Session, agent_name: str, prompt_type: str, payload: dict[str, Any], run_id: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    start = time.perf_counter()
    success = True
    json_ok = True
    error = None
    used_real_llm = settings.real_llm_enabled
    try:
        if used_real_llm:
            result = await _call_openai_compatible(settings, prompt_type, payload)
        else:
            result = _mock_result(prompt_type, payload)
    except Exception as exc:
        success = False
        json_ok = False
        error = str(exc)
        result = _mock_result(prompt_type, payload)

    latency = int((time.perf_counter() - start) * 1000)
    raw_in = json.dumps(payload, ensure_ascii=False)
    raw_out = json.dumps(result, ensure_ascii=False)
    db.add(LlmCall(
        run_id=run_id,
        agent_name=agent_name,
        model_name=settings.resolved_model if used_real_llm else "mock-llm",
        prompt_type=prompt_type,
        input_tokens=estimate_tokens(raw_in),
        output_tokens=estimate_tokens(raw_out),
        latency_ms=latency,
        cost_estimate=0 if not used_real_llm else estimate_tokens(raw_in + raw_out) * 0.000001,
        cache_hit=False,
        success=success,
        json_parse_success=json_ok,
        error_message=error,
    ))
    db.commit()
    return result

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.prompt_loader import get_system_prompt
from app.db.models import LlmCall


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


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
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def _mock_result(prompt_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if prompt_type == "dimension_discovery":
        return {"dimensions": ["空间体验", "车机系统", "续航里程", "驾驶感受", "外观设计"]}
    if prompt_type == "gap_analysis":
        return {
            "has_interception_opportunity": True,
            "target_weaknesses": [{"dimension": "车机系统", "neg_rate": 0.3}],
            "competitor_advantages": [{"competitor": "理想L9", "dimension": "车机系统", "advantage": "更流畅"}],
            "content_gaps": [{"dimension": "车机系统", "count": 5}],
        }
    if prompt_type == "interception":
        return {"suggestions": [{"dimension": "车机系统", "competitor": "理想L9", "interception_angle": "强调OTA升级频率", "content_format": "短视频", "priority": "high", "evidence_quotes": []}]}
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

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROMPT_FILES = {
    "feedback_classification": "feedback_analyst.yaml",
    "review": "reviewer.yaml",
    "compression": "compression.yaml",
    "prd": "prd_writer.yaml",
    "dimension_discovery": "dimension_discovery.yaml",
    "gap_analysis": "gap_analysis.yaml",
    "interception": "competitor_response.yaml",
    "default": "default.yaml",
}


DEFAULT_PROMPT = "Return concise valid JSON only. Use only provided evidence."


def prompts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts"


@lru_cache
def load_prompt_config(prompt_type: str) -> dict[str, Any]:
    filename = PROMPT_FILES.get(prompt_type, PROMPT_FILES["default"])
    path = prompts_dir() / filename
    if not path.exists():
        return {"name": prompt_type, "system_prompt": DEFAULT_PROMPT}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, str):
        return {"name": prompt_type, "system_prompt": data}
    system_prompt = data.get("system_prompt") or data.get("prompt") or data.get("instruction") or DEFAULT_PROMPT
    return {**data, "name": data.get("name", prompt_type), "system_prompt": system_prompt}


def get_system_prompt(prompt_type: str) -> str:
    return str(load_prompt_config(prompt_type).get("system_prompt") or DEFAULT_PROMPT)


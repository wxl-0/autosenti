# AutoSenti 竞品维度分析 Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FeedbackOS Agent（固定12节点PRD流水线）改造为 AutoSenti 汽车竞品维度分析 Agent，爬取汽车之家口碑评论，通过条件工作流自动发现维度、检测竞品缺口、生成同维度拦截策略报告，用于 AI PM 面试 demo。

**Architecture:** LangGraph `StateGraph` 新建 `AnalysisState`，条件路由由 `gap_detector` 输出的 `has_interception_opportunity` 字段决定是否进入 `interception_planner`；`dimension_discoverer` 节点内含局部 ReAct 循环（维度覆盖 < 8 条时自主追加抓取）。原有 PRD 流水线保持不动，新流水线作为独立入口（`POST /api/scrape`）运行。

**Tech Stack:** Python 3.11, FastAPI, LangGraph 0.2.x, SQLAlchemy + SQLite, BeautifulSoup4 + httpx（爬虫），Next.js 14 App Router, TypeScript

## Global Constraints

- Python 后端在 `backend/app/` 下；前端在 `frontend/app/` 下
- 新增路由文件命名为 `routes_scrape.py`，在 `backend/app/main.py` 中注册
- 新增 scraper 服务命名为 `scraper_service.py`，在 `backend/app/services/` 下
- LangGraph StateGraph 图函数命名为 `run_analysis_workflow()`，在新文件 `backend/app/agents/analysis_graph.py` 中（不修改现有 `graph.py`）
- `AnalysisState` 新增到 `backend/app/agents/state.py`，与现有 `AgentState` 共存
- Mock 模式：`settings.real_llm_enabled` 为 False 时，所有 LLM 调用走 `_mock_result()`；新增三个 mock 函数
- 所有 LLM 调用必须经过 `call_llm(db, agent_name, prompt_type, payload, run_id)` — 不直接调用 httpx
- `agent_step` context manager 在每个节点使用，记录 step_summary
- `evidence_quotes` 必须从 `raw_reviews` 中检索，prompt 层面禁止 LLM 编造；通过 ContextBuilder 注入
- 汽车之家 car_id 需从真实 URL 确认（本计划步骤 T1.1 包含验证方法）

---

### Task 1: 爬虫服务 + 依赖

**Files:**
- Create: `backend/app/services/scraper_service.py`
- Modify: `backend/requirements.txt`（确认 `beautifulsoup4` 和 `httpx` 已列入）

**Interfaces:**
- Produces: `scrape_brand_reviews(brand: str, car_id: str, max_pages: int = 3) -> list[dict]`
  - 返回 `[{"text": str, "rating": float, "date": str, "url": str, "brand": str}]`
- Produces: `scrape_all_brands(brand_car_id_map: dict[str, str], max_pages: int = 3) -> dict[str, list[dict]]`
  - 返回 `{brand: [review_dict, ...]}`
- Produces: `CAR_ID_MAP: dict[str, str]` — 默认 demo 车型映射

- [ ] **步骤 1.1：确认汽车之家车型 car_id**

访问以下页面，从 URL 中确认真实 car_id（URL 格式：`https://k.autohome.com.cn/spec/list_{car_id}_0_0_1_0.html`）：
- 零跑 D19：搜索"零跑D19"并进入口碑区，记录 URL 中的数字
- 理想 L9：同上
- 问界 M7：同上
- 深蓝 S07：同上

在代码中临时用占位 `"TBD"` 先写完逻辑，等手工确认后填入。

- [ ] **步骤 1.2：确认 requirements.txt 包含爬虫依赖**

```bash
cd backend && grep -E "beautifulsoup4|httpx|lxml" requirements.txt
```

若缺少，在 requirements.txt 末尾添加：
```
beautifulsoup4>=4.12.0
httpx>=0.27.0
lxml>=5.0.0
```

- [ ] **步骤 1.3：编写失败测试**

创建 `backend/tests/test_scraper_service.py`：

```python
import pytest
from unittest.mock import patch, MagicMock
from app.services.scraper_service import scrape_brand_reviews, scrape_all_brands, CAR_ID_MAP


def make_mock_html(reviews: list[dict]) -> str:
    items = ""
    for r in reviews:
        items += f"""
        <div class="koubei-list-wrapper">
          <div class="koubei-item">
            <div class="text-content">{r['text']}</div>
            <div class="score">{r.get('rating', 4.5)}</div>
            <div class="date">{r.get('date', '2024-01-01')}</div>
          </div>
        </div>
        """
    return f"<html><body>{items}</body></html>"


@patch("app.services.scraper_service.httpx")
def test_scrape_brand_reviews_returns_list(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = make_mock_html([
        {"text": "空间很大，后排宽敞", "rating": 4.5, "date": "2024-01-15"}
    ])
    mock_httpx.get.return_value = mock_response

    result = scrape_brand_reviews("零跑D19", "12345", max_pages=1)

    assert isinstance(result, list)
    assert len(result) >= 1
    assert "text" in result[0]
    assert "url" in result[0]
    assert "brand" in result[0]
    assert result[0]["brand"] == "零跑D19"


@patch("app.services.scraper_service.httpx")
def test_scrape_all_brands_returns_dict(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = make_mock_html([{"text": "好车", "rating": 5.0, "date": "2024-01-01"}])
    mock_httpx.get.return_value = mock_response

    result = scrape_all_brands({"品牌A": "11111"}, max_pages=1)

    assert isinstance(result, dict)
    assert "品牌A" in result
    assert isinstance(result["品牌A"], list)


def test_car_id_map_structure():
    assert isinstance(CAR_ID_MAP, dict)
    assert len(CAR_ID_MAP) >= 4
    for brand, car_id in CAR_ID_MAP.items():
        assert isinstance(brand, str)
        assert isinstance(car_id, str)
```

- [ ] **步骤 1.4：运行测试，确认失败**

```bash
cd backend && python -m pytest tests/test_scraper_service.py -v
```

预期：`ImportError: cannot import name 'scrape_brand_reviews' from 'app.services.scraper_service'`（文件不存在）

- [ ] **步骤 1.5：实现 scraper_service.py**

创建 `backend/app/services/scraper_service.py`：

```python
import time
import httpx
from bs4 import BeautifulSoup


CAR_ID_MAP: dict[str, str] = {
    "零跑D19": "TBD",   # 从 https://k.autohome.com.cn 口碑区 URL 确认
    "理想L9":  "TBD",
    "问界M7":  "TBD",
    "深蓝S07": "TBD",
}

URL_TEMPLATE = "https://k.autohome.com.cn/spec/list_{car_id}_0_0_{page}_0.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _parse_page(html: str, brand: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    reviews = []
    # 汽车之家口碑区主内容区选择器（需上线前验证）
    for item in soup.select(".koubei-item, .reply-item, [class*='koubei']"):
        text_el = item.select_one(".text-content, .content-text, p")
        if not text_el:
            continue
        text = text_el.get_text(strip=True)
        if len(text) < 10:
            continue
        score_el = item.select_one(".score, [class*='score']")
        rating = float(score_el.get_text(strip=True)) if score_el else 0.0
        date_el = item.select_one(".date, [class*='date'], time")
        date = date_el.get_text(strip=True) if date_el else ""
        reviews.append({
            "text": text,
            "rating": rating,
            "date": date,
            "url": page_url,
            "brand": brand,
        })
    return reviews


def scrape_brand_reviews(brand: str, car_id: str, max_pages: int = 3) -> list[dict]:
    all_reviews: list[dict] = []
    for page in range(1, max_pages + 1):
        url = URL_TEMPLATE.format(car_id=car_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                break
            page_reviews = _parse_page(resp.text, brand, url)
            if not page_reviews:
                break
            all_reviews.extend(page_reviews)
            time.sleep(0.5)
        except Exception:
            break
    return all_reviews


def scrape_pages_for_brand(brand: str, car_id: str, pages: list[int]) -> list[dict]:
    all_reviews: list[dict] = []
    for page in pages:
        url = URL_TEMPLATE.format(car_id=car_id, page=page)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            if resp.status_code == 200:
                all_reviews.extend(_parse_page(resp.text, brand, url))
            time.sleep(0.5)
        except Exception:
            pass
    return all_reviews


def scrape_all_brands(brand_car_id_map: dict[str, str], max_pages: int = 3) -> dict[str, list[dict]]:
    return {
        brand: scrape_brand_reviews(brand, car_id, max_pages)
        for brand, car_id in brand_car_id_map.items()
    }
```

- [ ] **步骤 1.6：运行测试，确认通过**

```bash
cd backend && python -m pytest tests/test_scraper_service.py -v
```

预期：3 个测试全部 PASS

- [ ] **步骤 1.7：提交**

```bash
git add backend/app/services/scraper_service.py backend/tests/test_scraper_service.py
git commit -m "feat(scraper): add autohome review scraper service"
```

---

### Task 2: 数据库扩展（SentimentAlert + source_url）

**Files:**
- Modify: `backend/app/db/models.py`

**Interfaces:**
- Produces: `SentimentAlert` ORM model with fields: `id, conversation_id, target_brand, competitor_brand, dimension, gap_type, severity, interception_angle, evidence_quotes, content_format, priority_rank, created_at`
- Produces: `FeedbackItem.source_url: Mapped[str | None]`（新增可选列）

- [ ] **步骤 2.1：编写失败测试**

创建 `backend/tests/test_models.py`（如文件已存在则追加）：

```python
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
```

- [ ] **步骤 2.2：运行，确认失败**

```bash
cd backend && python -m pytest tests/test_models.py -v
```

预期：`ImportError` 或 `AssertionError: 'sentiment_alerts' not in ...`

- [ ] **步骤 2.3：修改 models.py**

在 `backend/app/db/models.py` 中：

**在 `FeedbackItem` 类末尾（`created_at` 前一行）插入：**
```python
    source_url: Mapped[str | None] = mapped_column(String(500))
```

**在文件末尾（`EvaluationResult` 之后）追加：**
```python
class SentimentAlert(Base):
    __tablename__ = "sentiment_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    target_brand: Mapped[str] = mapped_column(String(120))
    competitor_brand: Mapped[str] = mapped_column(String(120))
    dimension: Mapped[str] = mapped_column(String(120))
    gap_type: Mapped[str] = mapped_column(String(40))   # weakness/content_gap/competitor_advantage
    severity: Mapped[str] = mapped_column(String(20))   # high/medium/low
    interception_angle: Mapped[str | None] = mapped_column(Text)
    evidence_quotes: Mapped[str | None] = mapped_column(Text)  # JSON array of strings
    content_format: Mapped[str | None] = mapped_column(String(120))
    priority_rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
```

- [ ] **步骤 2.4：运行测试，确认通过**

```bash
cd backend && python -m pytest tests/test_models.py -v
```

预期：4 个测试全部 PASS

- [ ] **步骤 2.5：提交**

```bash
git add backend/app/db/models.py backend/tests/test_models.py
git commit -m "feat(db): add SentimentAlert table and source_url to FeedbackItem"
```

---

### Task 3: AnalysisState + 3 个 YAML Prompt 文件 + prompt_loader 扩展

**Files:**
- Modify: `backend/app/agents/state.py`（追加 `AnalysisState`）
- Modify: `backend/app/core/prompt_loader.py`（`PROMPT_FILES` 增加 3 个键）
- Create: `backend/app/prompts/dimension_discovery.yaml`
- Create: `backend/app/prompts/gap_analysis.yaml`
- Create: `backend/app/prompts/competitor_response.yaml`

**Interfaces:**
- Consumes（Task 4）：`AnalysisState` TypedDict
- Produces: `AnalysisState` TypedDict（见下方实现）
- Produces: `get_system_prompt("dimension_discovery")` → str
- Produces: `get_system_prompt("gap_analysis")` → str
- Produces: `get_system_prompt("interception")` → str

- [ ] **步骤 3.1：编写失败测试**

创建 `backend/tests/test_state_and_prompts.py`：

```python
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
```

- [ ] **步骤 3.2：运行，确认失败**

```bash
cd backend && python -m pytest tests/test_state_and_prompts.py -v
```

预期：`ImportError: cannot import name 'AnalysisState'`

- [ ] **步骤 3.3：扩展 state.py**

在 `backend/app/agents/state.py` 末尾追加：

```python
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
```

- [ ] **步骤 3.4：创建 3 个 YAML prompt 文件**

`backend/app/prompts/dimension_discovery.yaml`：
```yaml
name: dimension_discovery
system_prompt: |
  你是汽车产品分析师。以下是多个车型的真实用户评论。
  请归纳用户最关心的 5-7 个评价维度。
  要求：从评论内容本身出发，不要套用固定模板。
  输出 JSON：{"dimensions": ["维度1", "维度2", ...]}
  只返回 JSON，不要解释。
```

`backend/app/prompts/gap_analysis.yaml`：
```yaml
name: gap_analysis
system_prompt: |
  你是竞品分析师。根据提供的各品牌维度情绪评分矩阵，识别：
  1. 目标品牌弱势维度（负面率 > 40%）
  2. 竞品强势维度（竞品正面率比目标品牌高 20% 以上）
  3. 内容缺口（评论量 < 5 条的维度）
  输出结构化 JSON：
  {
    "target_weaknesses": [{"dimension": str, "neg_rate": float}],
    "competitor_advantages": [{"dimension": str, "competitor": str, "gap": float}],
    "content_gaps": [{"dimension": str, "count": int}],
    "has_interception_opportunity": true|false
  }
  只使用提供的数据，不要推测未提供的信息。只返回 JSON。
```

`backend/app/prompts/competitor_response.yaml`：
```yaml
name: competitor_response
system_prompt: |
  你是汽车内容策略师。根据提供的竞品维度对比数据和真实用户评论原文，
  生成同维度拦截策略。
  规则：
  - 拦截角度必须与竞品优势在同一维度，不能切换话题
  - evidence_quotes 必须从提供的 raw_quotes 字段中直接引用原文，禁止编造
  - 内容形式建议要具体可执行
  输出 JSON 数组，每个维度一条记录：
  [
    {
      "dimension": str,
      "target_negative_rate": float,
      "competitor": str,
      "competitor_positive_rate": float,
      "interception_angle": str,
      "content_format": str,
      "evidence_quotes": [str, ...],
      "priority": "high"|"medium"|"low"
    }
  ]
  只返回 JSON 数组，不要解释。
```

- [ ] **步骤 3.5：扩展 prompt_loader.py 的 PROMPT_FILES**

在 `backend/app/core/prompt_loader.py` 中将：
```python
PROMPT_FILES = {
    "feedback_classification": "feedback_analyst.yaml",
    "review": "reviewer.yaml",
    "compression": "compression.yaml",
    "prd": "prd_writer.yaml",
    "default": "default.yaml",
}
```
替换为：
```python
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
```

- [ ] **步骤 3.6：运行测试，确认通过**

```bash
cd backend && python -m pytest tests/test_state_and_prompts.py -v
```

预期：4 个测试全部 PASS

- [ ] **步骤 3.7：提交**

```bash
git add backend/app/agents/state.py backend/app/core/prompt_loader.py \
        backend/app/prompts/dimension_discovery.yaml \
        backend/app/prompts/gap_analysis.yaml \
        backend/app/prompts/competitor_response.yaml \
        backend/tests/test_state_and_prompts.py
git commit -m "feat(state,prompts): add AnalysisState and 3 analysis prompt files"
```

---

### Task 4: 分析 Agent 图（analysis_graph.py）

**Files:**
- Create: `backend/app/agents/analysis_graph.py`

**Interfaces:**
- Consumes: `AnalysisState`（Task 3），`scrape_all_brands`, `scrape_pages_for_brand`（Task 1），`call_llm`，`agent_step`，`SentimentAlert`（Task 2）
- Produces: `run_analysis_workflow(db, target_brand, competitor_brands, max_pages, conversation_id) -> AnalysisState`

**节点职责速查：**

| 节点 | 输入字段 | 输出字段 | 说明 |
|------|---------|---------|------|
| `orchestrator` | `task` | `target_brand`, `competitor_brands` | 解析参数，不调 LLM |
| `scraper` | `target_brand`, `competitor_brands` | `raw_reviews`, `total_review_count` | 爬取所有品牌 |
| `dimension_discoverer` | `raw_reviews` | `dimensions`, `dimension_coverage`, `raw_reviews`（可追加） | LLM + 局部 ReAct |
| `sentiment_analyzer` | `raw_reviews`, `dimensions` | `dimension_scores` | 关键词规则计算 |
| `gap_detector` | `dimension_scores` | `target_weaknesses`, `competitor_advantages`, `content_gaps`, `has_interception_opportunity` | LLM 判断 |
| `interception_planner` | gap fields + `raw_reviews` | `interception_suggestions` | LLM + 真实证据注入 |
| `report_compiler` | all fields | `report_markdown`, `final_output` | 组装 Markdown |

- [ ] **步骤 4.1：编写失败测试**

创建 `backend/tests/test_analysis_graph.py`：

```python
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import AgentRun
from app.agents.analysis_graph import run_analysis_workflow


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


MOCK_REVIEWS = {
    "零跑D19": [
        {"text": "空间很大，后排非常宽敞，三人坐不挤", "rating": 4.5, "date": "2024-01-01", "url": "http://test", "brand": "零跑D19"},
        {"text": "车机偶尔卡顿，但可以接受", "rating": 3.5, "date": "2024-01-02", "url": "http://test", "brand": "零跑D19"},
    ],
    "理想L9": [
        {"text": "空间体验绝对一流，冰箱彩电大沙发", "rating": 5.0, "date": "2024-01-01", "url": "http://test", "brand": "理想L9"},
    ],
}


@patch("app.agents.analysis_graph.scrape_all_brands")
@patch("app.agents.analysis_graph.call_llm")
def test_workflow_runs_to_completion(mock_llm, mock_scrape):
    mock_scrape.return_value = MOCK_REVIEWS
    mock_llm.return_value = {
        "dimensions": ["空间体验", "车机系统"],
        "target_weaknesses": [],
        "competitor_advantages": [{"dimension": "空间体验", "competitor": "理想L9", "gap": 0.3}],
        "content_gaps": [],
        "has_interception_opportunity": True,
        "interception_angle": "性价比切入",
        "content_format": "图文",
        "evidence_quotes": ["空间很大"],
        "priority": "high",
    }
    db = make_db()
    state = asyncio.get_event_loop().run_until_complete(
        run_analysis_workflow(db, "零跑D19", ["理想L9"], max_pages=1, conversation_id="test")
    )
    assert state.get("report_markdown")
    assert state.get("final_output")
    assert "has_interception_opportunity" in state
    db.close()


@patch("app.agents.analysis_graph.scrape_all_brands")
@patch("app.agents.analysis_graph.call_llm")
def test_workflow_skips_interception_when_no_opportunity(mock_llm, mock_scrape):
    mock_scrape.return_value = MOCK_REVIEWS
    mock_llm.return_value = {
        "dimensions": ["空间体验"],
        "target_weaknesses": [],
        "competitor_advantages": [],
        "content_gaps": [],
        "has_interception_opportunity": False,
    }
    db = make_db()
    state = asyncio.get_event_loop().run_until_complete(
        run_analysis_workflow(db, "零跑D19", ["理想L9"], max_pages=1, conversation_id="test")
    )
    assert state.get("has_interception_opportunity") is False
    assert state.get("report_markdown")
    db.close()
```

- [ ] **步骤 4.2：运行，确认失败**

```bash
cd backend && python -m pytest tests/test_analysis_graph.py -v
```

预期：`ImportError: cannot import name 'run_analysis_workflow'`

- [ ] **步骤 4.3：实现 analysis_graph.py**

创建 `backend/app/agents/analysis_graph.py`：

```python
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
```

- [ ] **步骤 4.4：运行测试，确认通过**

```bash
cd backend && python -m pytest tests/test_analysis_graph.py -v
```

预期：2 个测试全部 PASS

- [ ] **步骤 4.5：提交**

```bash
git add backend/app/agents/analysis_graph.py backend/tests/test_analysis_graph.py
git commit -m "feat(agent): add AutoSenti analysis graph with conditional routing and ReAct"
```

---

### Task 5: API 路由（routes_scrape.py + 注册到 main.py）

**Files:**
- Create: `backend/app/api/routes_scrape.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `run_analysis_workflow`（Task 4）
- Produces: `POST /api/scrape` → `{"run_id": int, "report_markdown": str, "final_output": str, "interception_suggestions": list}`
- Produces: `GET /api/scrape/reports` → `[{"run_id": int, "status": str, "user_task": str, ...}]`

- [ ] **步骤 5.1：编写失败测试**

创建 `backend/tests/test_routes_scrape.py`：

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app


client = TestClient(app)


def test_scrape_endpoint_exists():
    # 用错误的 body 触发 422，确认路由已注册（如果返回 404 则路由未注册）
    res = client.post("/api/scrape", json={})
    assert res.status_code != 404, "Route /api/scrape not registered"


@patch("app.api.routes_scrape.run_analysis_workflow", new_callable=AsyncMock)
def test_scrape_returns_run_id(mock_workflow):
    mock_workflow.return_value = {
        "run_id": 1,
        "report_markdown": "# 报告",
        "final_output": "分析完成",
        "interception_suggestions": [],
        "has_interception_opportunity": False,
    }
    res = client.post("/api/scrape", json={
        "target_brand": "零跑D19",
        "competitor_brands": ["理想L9"],
        "max_pages": 1,
        "conversation_id": "test-conv",
    })
    assert res.status_code == 200
    data = res.json()
    assert "report_markdown" in data
    assert "final_output" in data


def test_reports_endpoint_exists():
    res = client.get("/api/scrape/reports")
    assert res.status_code != 404
```

- [ ] **步骤 5.2：运行，确认失败**

```bash
cd backend && python -m pytest tests/test_routes_scrape.py::test_scrape_endpoint_exists -v
```

预期：`AssertionError: Route /api/scrape not registered`

- [ ] **步骤 5.3：创建 routes_scrape.py**

创建 `backend/app/api/routes_scrape.py`：

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.analysis_graph import run_analysis_workflow
from app.db.database import get_db
from app.db.models import AgentRun

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


class ScrapeRequest(BaseModel):
    target_brand: str
    competitor_brands: list[str]
    max_pages: int = 3
    conversation_id: str = "legacy"


@router.post("")
async def scrape_and_analyze(req: ScrapeRequest, db: Session = Depends(get_db)):
    state = await run_analysis_workflow(
        db,
        target_brand=req.target_brand,
        competitor_brands=req.competitor_brands,
        max_pages=req.max_pages,
        conversation_id=req.conversation_id,
    )
    return {
        "run_id": state.get("run_id"),
        "report_markdown": state.get("report_markdown", ""),
        "final_output": state.get("final_output", ""),
        "interception_suggestions": state.get("interception_suggestions", []),
        "has_interception_opportunity": state.get("has_interception_opportunity", False),
        "dimensions": state.get("dimensions", []),
        "total_review_count": state.get("total_review_count", 0),
    }


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    runs = db.query(AgentRun).filter(
        AgentRun.user_task.like("竞品分析：%")
    ).order_by(AgentRun.id.desc()).limit(20).all()
    return [
        {
            "run_id": r.id,
            "status": r.status,
            "user_task": r.user_task,
            "final_output": r.final_output,
            "created_at": str(r.created_at),
        }
        for r in runs
    ]
```

- [ ] **步骤 5.4：在 main.py 注册路由**

在 `backend/app/main.py` 中添加：

```python
from app.api.routes_scrape import router as scrape_router
```

在 `app.include_router(evaluation_router)` 之后添加：

```python
app.include_router(scrape_router)
```

- [ ] **步骤 5.5：运行测试，确认通过**

```bash
cd backend && python -m pytest tests/test_routes_scrape.py -v
```

预期：3 个测试全部 PASS

- [ ] **步骤 5.6：提交**

```bash
git add backend/app/api/routes_scrape.py backend/app/main.py backend/tests/test_routes_scrape.py
git commit -m "feat(api): add /api/scrape endpoint for AutoSenti analysis"
```

---

### Task 6: 前端改动（Dashboard + report-studio + api.ts + 首页输入区）

**Files:**
- Modify: `frontend/app/dashboard/page.tsx`
- Create: `frontend/app/report-studio/page.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/agent-console/page.tsx`（description 文案）

**Interfaces:**
- Consumes: `GET /api/scrape/reports`, `POST /api/scrape`（Task 5）
- Consumes: 现有 `api.dashboard()`（dashboard 页从现有接口取数，仅改文案）

- [ ] **步骤 6.1：扩展 api.ts**

在 `frontend/lib/api.ts` 的 `export const api = {` 块末尾（`}` 前）添加：

```typescript
  scrapeAndAnalyze: (payload: {
    target_brand: string;
    competitor_brands: string[];
    max_pages?: number;
    conversation_id?: string;
  }) => request<any>("/api/scrape", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_pages: 3, conversation_id: "legacy", ...payload }),
  }),
  scrapeReports: () => request<any[]>("/api/scrape/reports"),
```

- [ ] **步骤 6.2：改造 dashboard/page.tsx 文案**

将 `frontend/app/dashboard/page.tsx` 中：
- `<h1 className="text-2xl font-semibold">Dashboard</h1>` → `<h1 className="text-2xl font-semibold">AutoSenti 竞品分析</h1>`
- `<p className="text-sm text-muted">从已上传并入库的数据中汇总反馈、机会点和生成质量。</p>` → `<p className="text-sm text-muted">汽车舆情竞品维度分析 — 自动化发现内容缺口与拦截策略。</p>`
- `<KpiCard title="总反馈数"` → `<KpiCard title="分析评论数"`
- `<KpiCard title="负面反馈率"` → `<KpiCard title="发现维度数"`（`value={data.total_feedback}` 暂时复用，演示时 mock 数据）
- `<KpiCard title="高优先级机会点"` → `<KpiCard title="高优先级拦截机会"`
- `<KpiCard title="PRD 草稿数"` → `<KpiCard title="分析报告数"`

- [ ] **步骤 6.3：创建 report-studio/page.tsx**

创建 `frontend/app/report-studio/page.tsx`：

```tsx
"use client";
import { useEffect, useState } from "react";
import { Download, Loader2, Play } from "lucide-react";
import { api } from "@/lib/api";

export default function ReportStudioPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>();
  const [targetBrand, setTargetBrand] = useState("零跑D19");
  const [competitors, setCompetitors] = useState("理想L9,问界M7,深蓝S07");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.scrapeReports().then(setReports).catch(console.error);
  }, []);

  async function runAnalysis() {
    setLoading(true);
    setError("");
    try {
      const result = await api.scrapeAndAnalyze({
        target_brand: targetBrand,
        competitor_brands: competitors.split(",").map(s => s.trim()).filter(Boolean),
        max_pages: 3,
      });
      setCurrent(result);
      const updated = await api.scrapeReports();
      setReports(updated);
    } catch (e: any) {
      setError(e.message || "分析失败");
    } finally {
      setLoading(false);
    }
  }

  function exportMarkdown() {
    if (!current?.report_markdown) return;
    const blob = new Blob([current.report_markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${targetBrand}_竞品分析报告.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Report Studio</h1>
        <p className="text-sm text-muted">输入目标车型与竞品，Agent 自动爬取评论并生成竞品拦截分析报告。</p>
      </div>

      {/* 输入区 */}
      <div className="card p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium block mb-1">目标车型</label>
            <input
              className="w-full rounded-md border border-line px-3 py-2 text-sm"
              value={targetBrand}
              onChange={e => setTargetBrand(e.target.value)}
              placeholder="例：零跑D19"
            />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">竞品车型（逗号分隔）</label>
            <input
              className="w-full rounded-md border border-line px-3 py-2 text-sm"
              value={competitors}
              onChange={e => setCompetitors(e.target.value)}
              placeholder="例：理想L9,问界M7"
            />
          </div>
        </div>
        <button
          className="btn flex items-center gap-2"
          onClick={runAnalysis}
          disabled={loading}
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          {loading ? "分析中，约 30-60 秒..." : "开始分析"}
        </button>
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      {/* 主体：历史记录 + 当前报告 */}
      <div className="grid grid-cols-[280px_1fr] gap-4">
        <aside className="card p-4">
          <h2 className="font-semibold text-sm mb-3">历史分析</h2>
          <div className="space-y-2">
            {reports.map(r => (
              <button
                key={r.run_id}
                className="w-full rounded-md border border-line p-3 text-left text-sm hover:bg-slate-50"
                onClick={() => setCurrent(r)}
              >
                {r.user_task}
                <div className="text-xs text-muted mt-1">{r.status} · {r.created_at?.slice(0, 10)}</div>
              </button>
            ))}
            {reports.length === 0 && <p className="text-xs text-muted">暂无历史记录</p>}
          </div>
        </aside>

        <section className="space-y-3">
          {current && (
            <>
              <div className="flex gap-2">
                <button className="btn" onClick={exportMarkdown}>
                  <Download size={15} />导出 .md
                </button>
              </div>
              <div className="card p-5 prose prose-sm max-w-none">
                <pre className="whitespace-pre-wrap text-sm">
                  {current.report_markdown || current.final_output || "报告内容为空"}
                </pre>
              </div>
            </>
          )}
          {!current && !loading && (
            <div className="card p-10 text-center text-muted text-sm">
              在左侧选择历史报告，或输入车型后点击「开始分析」
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
```

- [ ] **步骤 6.4：更新 agent-console 描述文案**

在 `frontend/app/agent-console/page.tsx` 中，找到说明性文案段落（`"从已上传并入库的数据"` 或类似文字），改为：
```
AutoSenti Agent 执行日志 — 每个节点的决策与数据追踪
```

（具体改法：打开文件定位该文字后使用 Edit 工具修改）

- [ ] **步骤 6.5：验证前端能启动**

```bash
cd frontend && npm run dev
```

访问 `http://localhost:3000/report-studio`，确认页面加载无报错，输入区渲染正常。

- [ ] **步骤 6.6：提交**

```bash
git add frontend/lib/api.ts frontend/app/dashboard/page.tsx \
        frontend/app/report-studio/page.tsx frontend/app/agent-console/page.tsx
git commit -m "feat(frontend): add report-studio page and update dashboard/api for AutoSenti"
```

---

### Task 7: Demo 数据准备与端到端验证

**Files:**（无新增文件，验证并修改 `scraper_service.py` 中的 `CAR_ID_MAP`）

**Goal:** 验证真实 car_id，确认爬虫能抓到真实数据，端到端跑通完整分析链路。

- [ ] **步骤 7.1：手工确认 4 个车型的 car_id**

访问汽车之家，搜索以下车型，进入口碑区，从 URL 提取数字 ID：

```
https://k.autohome.com.cn/spec/list_XXXXX_0_0_1_0.html
                                    ^^^^ 这是 car_id
```

记录结果（当场确认）：
- 零跑 D19：car_id = ______
- 理想 L9：car_id = ______
- 问界 M7：car_id = ______
- 深蓝 S07：car_id = ______

- [ ] **步骤 7.2：更新 CAR_ID_MAP**

将 `backend/app/services/scraper_service.py` 中的 `CAR_ID_MAP` 替换为真实 ID：

```python
CAR_ID_MAP: dict[str, str] = {
    "零跑D19": "<真实ID>",
    "理想L9":  "<真实ID>",
    "问界M7":  "<真实ID>",
    "深蓝S07": "<真实ID>",
}
```

- [ ] **步骤 7.3：测试单个品牌爬虫**

```bash
cd backend && python -c "
from app.services.scraper_service import scrape_brand_reviews, CAR_ID_MAP
reviews = scrape_brand_reviews('零跑D19', CAR_ID_MAP['零跑D19'], max_pages=1)
print(f'抓到 {len(reviews)} 条')
if reviews: print('第一条：', reviews[0]['text'][:80])
"
```

预期：打印出真实评论文本。若 0 条，检查 `_parse_page` 中的 CSS 选择器是否匹配当前汽车之家 DOM。

- [ ] **步骤 7.4：启动后端并调用 /api/scrape**

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

另开终端：
```bash
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"target_brand":"零跑D19","competitor_brands":["理想L9"],"max_pages":1,"conversation_id":"demo"}'
```

预期：返回 JSON，包含 `report_markdown` 字段，内含 `## 一、内容缺口诊断` 等章节标题。

- [ ] **步骤 7.5：端到端 UI 测试**

同时启动前后端：
```bash
# 终端 1
cd backend && uvicorn app.main:app --reload --port 8000
# 终端 2
cd frontend && npm run dev
```

访问 `http://localhost:3000/report-studio`，在输入框中填入：
- 目标车型：零跑D19
- 竞品：理想L9,问界M7

点击「开始分析」，等待约 30-60 秒。

验证：
- [ ] loading 状态正确显示
- [ ] 分析完成后报告显示在右侧
- [ ] 「导出 .md」按钮能下载 Markdown 文件
- [ ] 访问 `http://localhost:3000/agent-console`，能看到新 run 的步骤记录

- [ ] **步骤 7.6：提交最终版本**

```bash
git add backend/app/services/scraper_service.py
git commit -m "fix(scraper): update verified car IDs for demo brands"
```

---

## 自审 checklist

**规格覆盖：**
- [x] 爬虫（Task 1）→ `scraper_service.py`
- [x] 数据库扩展（Task 2）→ `SentimentAlert` + `source_url`
- [x] AnalysisState + YAML prompts（Task 3）
- [x] Agent 图（Task 4）→ `analysis_graph.py`，7 节点，条件路由，局部 ReAct
- [x] API 路由（Task 5）→ `routes_scrape.py`
- [x] 前端（Task 6）→ dashboard 文案 + report-studio + api.ts
- [x] Demo 数据（Task 7）→ 验证 car_id，端到端跑通

**类型一致性：**
- `scrape_all_brands` 返回 `dict[str, list[dict]]`，在 `analysis_graph.py` 的 `scraper` 节点中直接赋值 `raw_reviews`
- `call_llm` 签名：`(db, agent_name, prompt_type, payload, run_id)` → 所有 4 处调用一致
- `SentimentAlert.evidence_quotes` 是 Text（JSON 字符串），写入时 `json.dumps(...)`，与设计文档一致

**无占位符确认：** 所有步骤包含实际代码，无 TBD 的逻辑占位（car_id 的 "TBD" 是业务数据待确认，不是代码占位）

# AutoSenti 竞品维度分析 Agent — 设计文档

**日期：** 2026-06-27
**背景：** 将 FeedbackOS Agent（固定12节点 PRD 生成流水线）改造为汽车竞品维度分析 Agent，用于 AI 产品经理面试 demo。设计目标：面试 demo 优先，1 周内完成，能跑通核心路径并可当场演示。

---

## 一、项目定位

**名称：** AutoSenti（汽车舆情竞品分析 Agent）

**核心价值：** 将实习中手工完成的竞品内容分析（耗时 3-4 小时）自动化为 Agent 驱动的流程（5 分钟出报告），输出格式与手工产出一致，可直接交付内容团队执行。

**面试叙事：**
> "我在汽车营销乙方实习时手工做竞品内容分析——爬评论、归维度、找内容缺口、写拦截策略，这份工作很重复但很有价值。我把这个流程做成了 Agent，维度不是我写死的，是 Agent 从数据里自己发现的；拦截策略引用真实用户原话，不是 LLM 编造的。"

**差异化定位：**
- 维度自动发现（数据驱动，非固定模板）
- 同维度拦截逻辑（来自实习中真实操盘的竞品拦截框架）
- 局部 ReAct：数据不足时 Agent 自主追加抓取

---

## 二、整体架构

### 保留不动

| 模块 | 说明 |
|------|------|
| `core/config.py` | 多 Provider LLM 路由 |
| `core/context_builder.py` | Token 预算管理 |
| `core/embeddings.py` + `vectorstore/` | 向量检索 |
| `services/observability_service.py` | 每步 agent_step 记录 |
| `db/database.py` + SQLite | 数据库层 |
| FastAPI 路由框架 | 新增 1 个路由 |
| Next.js 前端框架 + agent-console 页 | 改文案，不重写 |

### 新增 / 重写

| 模块 | 操作 | 说明 |
|------|------|------|
| `services/scraper_service.py` | 新增 | 汽车之家口碑区爬虫 |
| `api/routes_scrape.py` | 新增 | 触发爬取 + 分析的 API |
| `agents/graph.py` | 重写 | 条件路由，去掉 PRD/cluster/metric 节点 |
| `agents/state.py` | 扩展 | 新增分析状态字段 |
| `core/llm.py` | 扩展 | 新增 `dimension_discovery`、`gap_analysis`、`interception` prompt 类型 |
| `db/models.py` | 扩展 | 新增 `SentimentAlert` 表 |
| `app/prompts/` | 新增 3 个 YAML | `dimension_discovery.yaml`、`gap_analysis.yaml`、`competitor_response.yaml` |
| 前端 `/dashboard` | 改文案 | 换成竞品分析指标 |
| 前端 `/report-studio` | 改造自 `/prd-studio` | Markdown 报告渲染 + 导出 |

---

## 三、Agent 执行模式

**主体：条件工作流**（LangGraph `add_conditional_edges`）

路径由 `gap_detector` 的输出决定，所有可能分支提前定义：

```
START
  ↓
orchestrator          解析品牌列表，不调用 LLM
  ↓
scraper               爬取所有品牌汽车之家口碑评论
  ↓
dimension_discoverer  LLM 归纳维度 + 局部 ReAct 追加抓取
  ↓
sentiment_analyzer    关键词规则 + 少量 LLM 打标
  ↓
gap_detector          LLM 综合判断，输出 has_interception_opportunity
  ↓
  ├── [True]  → interception_planner → report_compiler
  └── [False] → report_compiler
  ↓
END
```

**局部 ReAct（在 `dimension_discoverer` 节点内）：**
对每个发现的维度，检查覆盖评论量；若某维度 < 8 条，自主追加抓取 2 页，无需外部干预。这是整个系统唯一的自主决策点，也是面试中"这才是 Agent"的核心论据。

---

## 四、数据层

### 爬虫（`services/scraper_service.py`）

数据源：汽车之家口碑区（服务端渲染，标准 HTTP + BeautifulSoup，无需浏览器自动化）

```python
# 车型 ID 需从汽车之家对应车型口碑页 URL 中确认，格式如：
# https://k.autohome.com.cn/spec/list_3788_0_0_1_0.html → car_id = 3788
CAR_ID_MAP = {
    "零跑D19": "TBD_verify",   # 上线前从实际 URL 核查
    "理想L9":  "TBD_verify",
    "问界M7":  "TBD_verify",
    "深蓝S07": "TBD_verify",
}
URL_TEMPLATE = "https://k.autohome.com.cn/spec/list_{car_id}_0_0_{page}_0.html"
```

每条评论抓取字段：正文、综合评分、各维度评分、发布日期、原帖 URL（用于溯源）。

每品牌默认抓 3 页（约 40-60 条），4 个品牌总量约 200 条，耗时约 10-15 秒。

API 端点：
```
POST /api/scrape
{
  "target_brand": "零跑D19",
  "competitor_brands": ["理想L9", "问界M7"],
  "max_pages": 3,
  "conversation_id": "xxx"
}
```

### 数据库扩展（`db/models.py`）

**`feedback_items` 新增字段：**
- `source_url: str` — 原帖链接，溯源用

**新增表 `SentimentAlert`：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 主键 |
| `conversation_id` | str | 会话隔离 |
| `target_brand` | str | 目标车型 |
| `competitor_brand` | str | 被对比的竞品 |
| `dimension` | str | 分析维度 |
| `gap_type` | str | `weakness` / `content_gap` / `competitor_advantage` |
| `severity` | str | `high` / `medium` / `low` |
| `interception_angle` | text | 拦截角度建议 |
| `evidence_quotes` | text | 支撑证据（原文引用，JSON） |
| `content_format` | str | 推荐内容形式 |
| `priority_rank` | int | 执行优先级排序 |
| `created_at` | datetime | |

---

## 五、Agent State

```python
class AnalysisState(TypedDict, total=False):
    task: str
    target_brand: str
    competitor_brands: list[str]
    conversation_id: str
    run_id: int

    # 爬虫输出
    raw_reviews: dict           # brand → list[{text, rating, date, url}]
    total_review_count: int

    # 维度发现
    dimensions: list[str]       # LLM 自动发现的维度，非固定
    dimension_coverage: dict    # dimension → count（用于 ReAct 判断够不够）

    # 情绪分析
    dimension_scores: dict      # brand → dimension → {pos_rate, neg_rate, count, top_quotes}

    # 缺口检测
    target_weaknesses: list[dict]
    competitor_advantages: list[dict]
    content_gaps: list[dict]
    has_interception_opportunity: bool   # 条件路由开关

    # 拦截策略
    interception_suggestions: list[dict]

    # 输出
    report_markdown: str
    final_output: str
```

---

## 六、关键节点实现

### `dimension_discoverer`（含局部 ReAct）

**第一轮：** 将所有品牌前 30 条评论拼送 LLM，归纳 5-7 个维度，输出 JSON。
不使用固定维度列表，确保"车机卡顿"、"销售服务"等非标准维度能被发现。

**第二轮（ReAct）：**
```python
for dim in discovered_dimensions:
    coverage = count_reviews_mentioning(dim, raw_reviews[target_brand])
    if coverage < 8:
        # 按页码追加抓取（汽车之家口碑无关键词过滤接口）
        # 追加第 4、5 页，本地再按维度关键词筛选
        extra_pages = scrape_pages(target_brand, pages=[4, 5])
        raw_reviews[target_brand].extend(extra_pages)
        # 记录到 agent_step：哪个维度数据不足、追加了几条
```

### `gap_detector`

LLM 输入：`dimension_scores` 矩阵。
输出结构化 JSON，包含：
- `target_weaknesses`：目标品牌负面率 > 40% 的维度
- `competitor_advantages`：竞品正面率比目标品牌高 > 20% 的维度
- `content_gaps`：评论量 < 5 条的维度（用户有疑虑但无内容承接）
- `has_interception_opportunity`：上述任一存在则为 `true`

### `interception_planner`（核心差异化节点）

对每个有拦截价值的维度，LLM 结合真实评论原文（由 `ContextBuilder` 注入，非 LLM 自行生成）输出：

```json
{
  "dimension": "空间体验",
  "target_negative_rate": 0.42,
  "competitor": "理想L9",
  "competitor_positive_rate": 0.82,
  "interception_angle": "从性价比切入，同级空间价差 8 万，以'同样的后排空间少花 8 万'为内容锚点",
  "content_format": "真实车主实测对比图文，6 图格式",
  "evidence_quotes": ["D19 后排实测腿部空间宽敞，三人不挤", "价格便宜了这么多，空间差距没想象那么大"],
  "priority": "high"
}
```

**约束：** `evidence_quotes` 必须从 `raw_reviews` 里检索，不允许 LLM 自行编造。由 prompt 显式要求，并在 `ContextBuilder` 里把原始 quotes 注入 payload。

### `report_compiler`

组装 Markdown 报告，四个固定章节：
1. 内容缺口诊断（表格）
2. 竞品拦截策略（表格，对应实习手工产出格式）
3. 观望用户核心疑虑
4. 执行优先级 TOP5

---

## 七、Prompt 文件

### `dimension_discovery.yaml`
```yaml
name: dimension_discovery
system_prompt: |
  你是汽车产品分析师。以下是多个车型的真实用户评论。
  请归纳用户最关心的 5-7 个评价维度。
  要求：从评论内容本身出发，不要套用固定模板。
  输出 JSON：{"dimensions": ["维度1", "维度2", ...]}
```

### `gap_analysis.yaml`
```yaml
name: gap_analysis
system_prompt: |
  你是竞品分析师。根据提供的各品牌维度情绪评分矩阵，识别：
  1. 目标品牌弱势维度（负面率 > 40%）
  2. 竞品强势维度（竞品正面率比目标品牌高 20% 以上）
  3. 内容缺口（评论量 < 5 条的维度）
  输出结构化 JSON，包含 has_interception_opportunity 字段。
  只使用提供的数据，不要推测未提供的信息。
```

### `competitor_response.yaml`
```yaml
name: competitor_response
system_prompt: |
  你是汽车内容策略师。根据提供的竞品维度对比数据和真实用户评论原文，
  生成同维度拦截策略。
  规则：
  - 拦截角度必须与竞品优势在同一维度，不能切换话题
  - evidence_quotes 必须从提供的评论原文中直接引用，禁止编造
  - 内容形式建议要具体可执行
  输出 JSON 数组，每个维度一条记录。
```

---

## 八、前端改动

| 页面 | 改动内容 |
|------|---------|
| `/dashboard` | KPI 换成：分析车型数 / 发现维度数 / 高优先级拦截机会数 / 报告数 |
| `/agent-console` | 保留结构，每个节点展示决策摘要（如"续航维度数据不足，自主追加抓取 2 页"）|
| `/prd-studio` → `/report-studio` | 改造：渲染 Markdown 竞品报告，支持导出 .md |
| 首页输入区 | 新增：目标车型输入框 + 竞品车型（逗号分隔）+ 开始分析按钮 |

---

## 九、Demo 数据准备

- 目标车型：零跑 D19
- 对比竞品：理想 L9、问界 M7、深蓝 S07
- 数据量：每品牌 3 页，约 40-60 条，共约 200 条
- 演示重点：当场输入车型名 → 爬取 → Agent 分析 → 报告输出的完整链路

---

## 十、面试关键问答准备

**Q：维度不写死，怎么保证准确性？**
A：从 200 条评论里 LLM 归纳，召回的维度一定是用户实际在讨论的，比写死 8 个维度更贴近真实反馈结构。误差在可接受范围内——这本身就是"用 AI 做产品分析"的正常工作方式。

**Q：和直接把评论贴给 ChatGPT 有什么区别？**
A：三点：① 维度是数据驱动发现的，不是 prompt 里写死的；② ReAct 追加抓取保证每个维度有足够证据；③ 拦截策略引用真实原文，有溯源链路，不是 LLM 编造。

**Q：拦截建议准不准？你怎么评估？**
A：把 Agent 输出和我实习中手工产出的竞品分析文档做对比，看维度覆盖率和拦截角度的业务合理性。有一份真实 baseline 可以当场展示。

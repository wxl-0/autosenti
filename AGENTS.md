# CLAUDE.md

This file provides guidance to Codex when working with this repository.

## 项目简介

AutoSenti 是面向汽车营销团队的竞品口碑情报系统。通过抓取汽车之家口碑 JSON API，经 LangGraph 分析流水线输出维度评分矩阵、优劣势对比和内容策略建议，服务达人投放 brief 制定与官号内容规划。

## 常用命令

### 后端

```bash
cd backend && pip install -e .
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend && npm install
cd frontend && npm run dev      # http://localhost:3000
cd frontend && npm run build
```

### 环境变量

`.env` 放在**项目根目录**：

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=...        # 兼容接口，如 DashScope / DeepSeek / SiliconFlow
OPENAI_MODEL=qwen-plus
USE_MOCK_LLM=false         # true = 无需 API Key 的本地调试模式
```

## 架构说明

### 后端（`backend/app/`）

**分析流水线** — `agents/analysis_graph.py`，LangGraph `StateGraph`，7 个节点：

```
orchestrator → scraper → dimension_discoverer → sentiment_analyzer → gap_detector
                                                                     ↓ has_opportunity?
                                                       interception_planner → report_compiler
                                                                     ↓ no
                                                                  report_compiler
```

状态类型：`AnalysisState`（TypedDict，定义于 `agents/state.py`）。

**触发入口**：
- `POST /api/scrape` — 同步返回完整 JSON 结果
- `POST /api/scrape/stream` — SSE 流式推送节点进度，最终返回报告

SSE 实现：`asyncio.Queue` + `FastAPI StreamingResponse`，`run_analysis_workflow` 接受 `progress_queue` 参数，每个节点 `await _emit(step, message)` 推送进度。

**爬虫服务** — `services/scraper_service.py`：
- 汽车之家口碑 API：`https://koubeiipv6.app.autohome.com.cn/pc/series/list?pm=3&seriesId={id}&pageIndex={page}&pageSize=20`
- `CAR_ID_MAP`：16 款车型的 series_id 映射
- `COMPETITOR_MAP`：零跑 D19 / C10 / C11 / C16 的预设竞品组合

**评分计算** — `analysis_graph.py:_compute_dimension_scores()`：
- 直接取 API `scoreList` 字段（1-5 整数，用户手动打分）
- 计算 avg_score、pos_rate（≥4）、neg_rate（≤2）
- `STANDARD_DIMENSIONS`：`["空间", "驾驶感受", "续航", "外观", "内饰", "性价比", "智能化"]`

**报告生成** — `report_compiler` 节点：
- `_validated_strengths()`：从实际评分重新验证 LLM 返回的优势，只展示 score_gap ≥ 0 的维度
- `_pos_quote()` / `_neg_quote()`：用正则从完整评论文本中提取满意/不满意部分
- 竞品画像维度通过 `STANDARD_DIMS_SET` 过滤，防止 LLM 造维度

**LLM 调用层** — `core/llm.py`：
- `call_llm()` 是唯一入口
- `_render_user_content()` 渲染 YAML 中的 `user_template`（`{variable}` 占位符）
- `USE_MOCK_LLM=true` 时返回 `_mock_result()`，保证本地无 API Key 可跑通

**Prompt 管理** — `app/prompts/`：
- `gap_analysis.yaml`：输出 executive_summary、our_strengths（只填真实领先维度）、our_gaps
- `competitor_response.yaml`：输出 competitor_profiles（维度限定为标准 7 个）、suggestions
- `dimension_discovery.yaml`：备用维度发现（当前主要用 scoreList 直接取）

**数据库** — SQLite，路径 `backend/storage/feedbackos.db`。核心表：
- `agent_runs`：每次分析任务记录，含 `report_markdown` 字段
- `agent_steps`：各节点执行日志
- `llm_calls`：LLM 调用记录
- `sentiment_alerts`：竞品拦截策略条目

**API 路由**：
- `app/api/routes_scrape.py`：`/api/scrape`、`/api/scrape/stream`、`/api/scrape/reports`
- `app/api/routes_conversation.py`：会话管理

### 前端（`frontend/`）

Next.js 14 App Router，单页面 `app/report-studio/page.tsx`。

- 下拉选择目标车型，自动填入 `PRESET_COMPETITORS` 预设竞品
- `api.scrapeAndAnalyzeStream()` — `async function*`，通过 `fetch` + `ReadableStream` 消费 SSE
- `for await` 循环更新 `progressMessages`，实时展示节点进度
- 报告用 `react-markdown` + `remark-gfm` 渲染，样式在 `globals.css` 的 `.markdown-body`
- 历史记录从 `GET /api/scrape/reports` 加载，左侧 sidebar 展示

## 关键设计约定

- **评分不经 LLM 判断**：直接取 scoreList 均值，LLM 只做文字解读和内容策略建议
- **优势必须代码验证**：`_validated_strengths()` 从实际数据重算，防止 LLM 返回错误 score_gap 方向
- **维度边界硬限制**：竞品画像的维度必须来自 `STANDARD_DIMS_SET`，代码层过滤 + prompt 层约束双保险
- **Mock LLM 结构一致**：`_mock_result()` 对 gap_analysis 和 interception 都返回合法字段结构

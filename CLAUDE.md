# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## 项目简介

FeedbackOS Agent 是一款产品反馈分析工具。用户上传反馈文件（CSV、Excel、TXT、DOCX），AI Agent 流水线自动完成痛点聚类、机会点评分、PRD 草稿生成与评审。系统支持多家 LLM 提供商（OpenAI、DashScope/Qwen、DeepSeek、SiliconFlow），也可完全离线运行（Mock LLM 模式）。

## 常用命令

### 后端

```bash
# 首次安装（可编辑模式）
cd backend && pip install -e .

# 启动开发服务器
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend && npm install      # 首次安装
cd frontend && npm run dev      # http://localhost:3000
cd frontend && npm run build
cd frontend && npm run lint
```

### 基础设施

```bash
# 启动 Redis（运行时依赖）
docker-compose up -d redis
```

### 环境变量

`.env` 文件放在**项目根目录**（不是 `backend/` 内），config.py 读取路径为 `../env`：

```env
OPENAI_API_KEY=sk-...          # 或 DASHSCOPE_API_KEY / DEEPSEEK_API_KEY / SILICONFLOW_API_KEY
OPENAI_MODEL=gpt-4o-mini       # 可选，覆盖默认模型
OPENAI_BASE_URL=...            # 可选，自定义接入点
USE_MOCK_LLM=false             # true = 无需 API Key 的本地调试模式
USE_MILVUS=false               # true = 使用 Milvus；false = 内存向量库（默认）
```

不创建 `.env` 也能运行——检测不到 API Key 时自动激活 Mock LLM 模式。

## 架构说明

### 后端（`backend/app/`）

**原有 PRD Agent 流水线** — `agents/graph.py` 用 LangGraph `StateGraph` 定义完整流程，节点线性执行：

```
orchestrator → file_intake → data_intake → feedback_analyst → retrieval
→ cluster → metric → opportunity → compression → prd_writer → reviewer → final_compression
```

所有节点共用 `AgentState`（TypedDict，定义于 `agents/state.py`）。每个节点通过 `services/observability_service.py` 的 `agent_step()` 上下文管理器包裹，自动写入 SQLite 的 `agent_steps` 表并记录耗时。

**AutoSenti 竞品分析流水线** — `agents/analysis_graph.py`，独立的 LangGraph 图，节点含条件边：

```
orchestrator → scraper → dimension_discoverer → sentiment_analyzer → gap_detector
                                                                    ↓ has_opportunity?
                                                      interception_planner → report_compiler
                                                                    ↓ no
                                                                 report_compiler
```

- 状态类型：`AnalysisState`（TypedDict，定义于 `agents/state.py`，与 `AgentState` 并列）。
- `dimension_discoverer` 含局部 ReAct：维度覆盖不足（< 8 条）时自动追加抓取第 4-5 页。
- 触发入口：`POST /api/scrape`，由 `api/routes_scrape.py` 路由。

**爬虫服务** — `services/scraper_service.py`：
- 爬取汽车之家口碑区（`https://k.autohome.com.cn/{series_id}/index_{page}.html`）。
- `CAR_ID_MAP` 维护默认四款车的 series_id：零跑D19(`8273`)、理想L9(`6576`)、蔚来ES6(`4881`)、深蓝S07(`6817`)。
- 公开 API：`scrape_brand_reviews()`、`scrape_pages_for_brand()`、`scrape_all_brands()`。

**LLM 调用层** — `core/llm.py`：
- `call_llm()` 是唯一的 LLM 调用入口。
- 每次调用前，payload 都经过 `ContextBuilder`（`core/context_builder.py`）做 token 预算截断，并记录压缩指标。
- `real_llm_enabled` 为 false 时直接返回 `_mock_result()`（基于规则，不调用 API）。
- prompt_type 映射到 `app/prompts/` 下对应的 YAML 文件（见 `core/prompt_loader.py`）。

**多 Provider 路由** — `core/config.py` 根据环境变量自动识别：DashScope → Qwen 模型，DeepSeek → deepseek-chat，其余使用 OpenAI 兼容接口。

**向量库** — `vectorstore/milvus_client.py`：`VectorClient` 以 Milvus Lite 为主，自动降级到内存向量库（`vectorstore/fallback_vectorstore.py`）。`USE_MILVUS=false`（默认）时所有向量数据仅存内存，重启后丢失。

**数据库** — SQLite，路径 `backend/storage/feedbackos.db`（启动时自动创建）。所有模型定义在 `db/models.py`。核心表：`feedback_items`、`insight_clusters`、`opportunities`、`prd_documents`、`agent_runs`、`agent_steps`、`llm_calls`、`retrieval_logs`、`sentiment_alerts`。

**数据隔离** — 每条记录都携带 `project_id`（目前固定为 `1`）和 `conversation_id`（UUID 字符串）。Conversation 是会话边界，上传文件、反馈、聚类、机会点、PRD 全部按 `conversation_id` 隔离。

**API 路由** — 每个功能域有独立的 `api/routes_*.py`，统一挂载在 `/api/` 前缀下。原有 Agent 工作流通过 `POST /api/agent/run` 触发；AutoSenti 竞品分析通过 `POST /api/scrape` 触发，历史记录通过 `GET /api/scrape/reports` 查询。

### 前端（`frontend/`）

Next.js 14 App Router。页面：`/dashboard`、`/feedback`、`/agent-console`、`/prd-studio`、`/report-studio`（AutoSenti 竞品分析）。所有 API 请求通过 `lib/api.ts` 封装。UI 使用 Tailwind CSS + Recharts + Framer Motion。

### Prompt 管理

Agent 系统提示存放在 `backend/app/prompts/` 下的 YAML 文件中，`prompt_type` 字符串到文件名的映射在 `core/prompt_loader.py`。提示内容使用 `lru_cache` 缓存，修改 YAML 后需重启服务才生效。

AutoSenti 新增三个 prompt 文件：`dimension_discovery.yaml`、`gap_analysis.yaml`、`competitor_response.yaml`。

## 关键设计约定

- **原始文件不传给 LLM。** `ContextBuilder` 只传结构化记录、检索到的证据和任务元数据。
- **所有查询必须按 `conversation_id` 过滤。** 新增 Agent 节点或数据查询时，始终加 `conversation_id` 条件，避免跨会话数据污染。
- **Mock LLM 必须与真实模式输出结构一致。** `core/llm.py` 中的 `_mock_result()` 对每种 prompt_type 都需返回合法的字段结构，保证本地开发无需 API Key 也能跑通完整流水线。

# FeedBackOS

面向产品经理的 Chat-first AI 需求发现工作台，用于用户反馈分析、机会点发现和 PRD 生成。同时内置 **AutoSenti** 竞品分析模块，通过爬取汽车之家口碑评论，自动发现内容缺口与拦截策略。

FeedBackOS 支持用户在一个聊天会话中上传真实业务文件。系统会先完成文件解析、字段识别、清洗、结构化入库和向量化，再通过多 Agent workflow 分析痛点、生成机会点、撰写 PRD，并由 Reviewer 对生成结果进行质量评审。

## 预览

<img width="1908" height="953" alt="FeedBackOS workspace" src="https://github.com/user-attachments/assets/57d6456d-e55a-43fc-99a7-75ba02369be2" />
<img width="1908" height="953" alt="FeedBackOS feedback inbox" src="https://github.com/user-attachments/assets/3b856340-ca4a-47f1-af37-b77bd1d578d1" />
<img width="1908" height="953" alt="FeedBackOS PRD panel" src="https://github.com/user-attachments/assets/1380e5b7-4fae-4847-b77b-251e49fcfa02" />

## 功能特性

- Chat-first Agent Workspace，在聊天页面上传文件并发起分析任务。
- 基于 `conversation_id` 的会话级数据隔离。
- 支持 CSV、Excel、TXT、Markdown、DOCX 文件上传和解析。
- 自动识别反馈字段、指标字段和文本类文件。
- 反馈分类：情绪、严重度、产品模块、问题类型、一句话摘要。
- 轻量 RAG 流程：解析、清洗、入库、向量化、检索、压缩，再调用 LLM。
- LangGraph 多 Agent workflow：反馈分析、痛点聚类、机会点评分、PRD 生成、Reviewer 评审。
- 支持在同一会话中生成多份不同痛点的 PRD。
- PRD 历史面板，支持切换、编辑、保存、导出 Markdown 和 DOCX。
- Reviewer 面板，展示综合评分、证据覆盖、问题和建议。
- Evaluation 面板，展示 Agent、LLM、证据、Reviewer 和上下文压缩指标。
- **AutoSenti 竞品分析**：爬取汽车之家口碑评论，自动发现维度差距与内容拦截策略，在 `/report-studio` 页面一键生成竞品分析报告。
- 支持真实 LLM 和 Mock LLM 双模式。
- 没有 Redis、Milvus 或真实 API Key 时，仍可通过 fallback/mock 跑完整流程。

## 技术栈

前端：

- Next.js
- TypeScript
- Tailwind CSS
- Recharts
- lucide-react

后端：

- FastAPI
- Python 3.11+
- LangGraph
- SQLAlchemy
- SQLite
- Pydantic
- Uvicorn
- python-docx

AI 与检索：

- OpenAI-compatible Chat Completions API
- OpenAI-compatible Embeddings API
- YAML Prompt 管理
- Mock LLM
- Mock embedding
- Milvus / Milvus Lite 可选
- In-memory fallback vector store
- Redis 可选

## 系统架构

```mermaid
flowchart LR
  U[Browser] --> FE[Next.js Workspace]
  FE --> API[FastAPI]
  API --> DB[(SQLite)]
  API --> AG[LangGraph Workflow]
  AG --> VS[Vector Store Facade]
  VS --> FB[In-memory Fallback]
  VS -. optional .-> MILVUS[Milvus / Milvus Lite]
  AG --> LLM{LLM Gateway}
  LLM --> REAL[OpenAI-compatible API]
  LLM --> MOCK[Mock LLM]
  API -. optional .-> REDIS[Redis]
```

## Agent Workflow

### 原有 PRD 生成流水线

```mermaid
flowchart TD
  A[用户任务] --> B[Orchestrator]
  B --> C[File Intake]
  C --> D[Data Intake]
  D --> E[Feedback Analyst]
  E --> F[Retrieval]
  F --> G[Cluster]
  G --> H[Metric Analyst]
  H --> I[Opportunity]
  I --> J[Compression]
  J --> K[PRD Writer]
  K --> L[Reviewer]
  L --> M[Final Reply]
```

当前 workflow 以固定顺序为主。`Opportunity` 节点会根据用户输入选择目标痛点，例如用户输入：

```text
写一份针对支付体验痛点的 PRD
```

系统会优先选择支付相关机会点生成 PRD，而不是始终选择最高优先级机会点。

### AutoSenti 竞品分析流水线

```mermaid
flowchart TD
  A[POST /api/scrape] --> B[Orchestrator]
  B --> C[Scraper\n爬取汽车之家口碑]
  C --> D[DimensionDiscoverer\n发现评价维度]
  D --> E[SentimentAnalyzer\n计算情绪评分矩阵]
  E --> F[GapDetector\n识别内容缺口]
  F -->|有拦截机会| G[InterceptionPlanner\n生成拦截策略]
  F -->|无拦截机会| H[ReportCompiler\n生成 Markdown 报告]
  G --> H
```

入口：`/report-studio` 页面，输入目标车型和竞品后一键触发。结果存入 `sentiment_alerts` 表，报告支持导出 `.md`。

## 数据处理流程

上传文件不会直接整体进入大模型。

```text
上传文件
→ 文件解析
→ 字段识别或文本类型识别
→ 清洗和标准化
→ 写入 SQLite
→ 生成 embedding
→ 按 conversation_id 检索相关证据
→ 压缩上下文
→ 仅将相关压缩证据发送给 LLM
```

支持文件类型：

- CSV / Excel：反馈表或指标表。
- TXT / Markdown / DOCX：用户访谈、调研笔记、会议纪要、历史 PRD、版本复盘。

主要数据表：

- `conversations`, `conversation_messages`
- `uploaded_files`, `data_sources`
- `feedback_items`, `metric_snapshots`, `document_chunks`
- `insight_clusters`, `opportunities`, `prd_documents`
- `agent_runs`, `agent_steps`
- `llm_calls`, `retrieval_logs`, `compression_logs`
- `project_memory`, `decision_memory`, `user_preference_memory`
- `sentiment_alerts`（AutoSenti 竞品拦截策略）

## Prompt 管理

Prompt 统一放在：

```text
backend/app/prompts/
```

运行时由下面的 loader 读取和缓存：

```text
backend/app/core/prompt_loader.py
```

当前接入的 prompt 文件：

- `feedback_analyst.yaml`
- `prd_writer.yaml`
- `reviewer.yaml`
- `compression.yaml`
- `default.yaml`
- `dimension_discovery.yaml`（AutoSenti：发现评价维度）
- `gap_analysis.yaml`（AutoSenti：识别内容缺口）
- `competitor_response.yaml`（AutoSenti：生成拦截策略）

每个 prompt 文件包含元信息和 `system_prompt`：

```yaml
name: prd_writer
version: 1
owner: prd_writer_agent
response_format: json_object
system_prompt: |
  ...
```

`llm.py` 只负责模型选择、LLM 调用、Mock fallback 和调用日志记录。

## 本地运行

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:3000
```

后端健康检查：

```text
http://localhost:8000/health
```

## 环境变量

复制 `.env.example` 为 `.env`，放在项目根目录。

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v4
USE_MOCK_LLM=false

DATABASE_URL=sqlite:///./storage/feedbackos.db
REDIS_URL=redis://localhost:6379/0
USE_MILVUS=false
MILVUS_URI=
MILVUS_LITE_PATH=./storage/milvus_lite.db
MAX_CONTEXT_TOKENS=6000
CONTEXT_RESERVED_OUTPUT_TOKENS=1500
FRONTEND_ORIGIN=http://localhost:3000
```

如果没有真实模型 Key：

```env
USE_MOCK_LLM=true
```

默认情况下，向量检索使用内存 fallback，适合本地快速演示。要切换到 Milvus Lite：

```env
USE_MILVUS=true
MILVUS_LITE_PATH=./storage/milvus_lite.db
```

要连接独立 Milvus 服务：

```env
USE_MILVUS=true
MILVUS_URI=http://localhost:19530
```

如果 Milvus 初始化、写入或检索失败，系统会自动回退到内存向量检索，保证上传、分析和 PRD 生成流程不中断。

上下文窗口由后端统一控制：

- `MAX_CONTEXT_TOKENS`：单次 LLM 调用的上下文预算。
- `CONTEXT_RESERVED_OUTPUT_TOKENS`：为模型输出预留的 token 数。
- LLM 调用前会先经过 `ContextBuilder`，只发送结构化数据、检索证据和摘要，不发送完整原始文件。
- 如果 payload 超过预算，系统会裁剪证据列表、压缩历史消息、截断长文本，并写入 `compression_logs`。


## 项目结构

```text
feedbackos-agent/
  backend/
    app/
      agents/
      api/
      core/
      db/
      prompts/
      services/
      vectorstore/
    uploads/
    storage/
    requirements.txt
    pyproject.toml
  frontend/
    app/
    components/
    lib/
  README.md
  README-ZH.md
  .env.example
  docker-compose.yml
```

运行时目录：

- `backend/uploads/`：用户上传文件。
- `backend/storage/exports/`：导出文件，例如 DOCX。
- `backend/storage/prds/`：PRD 存储目录预留。
- `backend/storage/feedbackos.db`：本地 SQLite 数据库。

这些运行时文件已加入 `.gitignore`，不会上传到 GitHub。

## 测试流程

### 原有 PRD 生成流程

1. 启动后端和前端。
2. 打开 `http://localhost:3000`。
3. 上传反馈 CSV、Excel、TXT、Markdown 或 DOCX 文件。
4. 查看 `当前文件` 和 `Feedback Inbox`。
5. 输入：

```text
分析当前反馈并生成机会点
```

6. 输入：

```text
写一份针对支付体验痛点的 PRD
```

7. 查看 `Insight Cluster`、`PRD`、`Reviewer` 和 `Evaluation` 面板。

### AutoSenti 竞品分析流程

1. 启动后端和前端（需要真实 API Key，爬虫需访问汽车之家）。
2. 打开 `http://localhost:3000/report-studio`。
3. 目标车型填 `零跑D19`，竞品填 `理想L9,蔚来ES6,深蓝S07`。
4. 点击「开始分析」，等待约 30-60 秒。
5. 查看生成的竞品维度分析报告，可点击「导出 .md」下载。
6. 历史分析记录显示在左侧 sidebar，点击可查看往期报告。

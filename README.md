# AutoSenti — 汽车竞品口碑情报系统

面向汽车营销团队的竞品内容情报工具。自动抓取汽车之家口碑评论，通过 LangGraph 分析流水线输出维度评分矩阵、优劣势对比和内容策略建议，帮助内容运营团队制定达人投放 brief 和官号选题方向。

## 功能

- **一键分析**：输入目标车型与竞品，自动抓取汽车之家口碑数据并完成分析
- **维度评分矩阵**：覆盖空间、驾驶感受、续航、外观、内饰、性价比、智能化 7 个维度，标注负面率
- **优劣势识别**：从实际评分数据验证，只展示真实领先/落后的维度，附用户原声
- **竞品深度画像**：每个竞品的用户认可点与高频吐槽，可直接转化为拦截内容方向
- **SSE 流式进度**：分析过程实时推送节点进度，无需等待 loading
- **历史报告**：所有分析结果持久化，左侧 sidebar 随时调取历史记录
- **导出 Markdown**：一键导出完整报告

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 14 · TypeScript · Tailwind CSS · react-markdown |
| 后端 | FastAPI · Python 3.11 · LangGraph · SQLAlchemy |
| 数据库 | SQLite（本地持久化） |
| AI | OpenAI-compatible API |
| 爬虫 | 汽车之家口碑 JSON API（scoreList 结构化评分） |

## 系统架构

```
Browser → Next.js → FastAPI → LangGraph Pipeline → SQLite
                      ↑                ↓
                   SSE Stream    汽车之家 API + LLM
```

## 分析流水线

```
POST /api/scrape/stream
        │
        ▼
  Orchestrator（解析任务参数）
        │
        ▼
   Scraper（抓取多品牌口碑数据）
        │
        ▼
  DimensionDiscoverer（验证 7 维度覆盖度）
        │
        ▼
  SentimentAnalyzer（计算品牌×维度评分矩阵）
        │
        ▼
   GapDetector（LLM 分析优劣势，输出执行摘要）
        │
   ┌────┴────┐
   │有拦截机会  │无
   ▼          ▼
InterceptionPlanner  ReportCompiler
（LLM 生成竞品画像）       │
        │              ▼
        └──────► 输出 Markdown 报告
```

## 快速开始

**环境要求**：Python 3.11+、Node.js 18+

### 1. 配置环境变量

在项目根目录创建 `.env`：

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 或其他兼容接口
OPENAI_MODEL=qwen-plus
USE_MOCK_LLM=false
```

> 不配置 API Key 时自动启用 Mock LLM 模式，可跑通完整流程但报告内容为模拟数据。

### 2. 启动后端

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 [http://localhost:3000](http://localhost:3000)，自动跳转到分析页面。

## 使用方式

1. 从下拉菜单选择目标车型（零跑 D19 / C10 / C11 / C16），竞品自动填入
2. 也可手动输入任意车型名称（需在 `CAR_ID_MAP` 中有对应 series_id）
3. 点击「开始分析」，实时查看各节点进度
4. 分析完成后查看报告，可导出 `.md` 文件

**内置预设车型**

| 目标车型 | 预设竞品 |
|---|---|
| 零跑 D19 | 理想 L9、蔚来 ES6、深蓝 S07 |
| 零跑 C10 | 银河 E5、银河 L7、深蓝 S05、尚界 H5 |
| 零跑 C11 | 深蓝 S05、深蓝 S07、尚界 H5、元 PLUS |
| 零跑 C16 | 银河 M9、理想 L6、eπ008、唐 |

## 项目结构

```
autosenti/
├── backend/
│   └── app/
│       ├── agents/
│       │   ├── analysis_graph.py   # LangGraph 分析流水线
│       │   └── state.py            # AnalysisState 类型定义
│       ├── api/
│       │   ├── routes_scrape.py    # /api/scrape + /api/scrape/stream
│       │   └── routes_conversation.py
│       ├── core/
│       │   ├── llm.py              # LLM 调用 + Mock 模式
│       │   └── prompt_loader.py
│       ├── prompts/
│       │   ├── gap_analysis.yaml
│       │   └── competitor_response.yaml
│       └── services/
│           └── scraper_service.py  # 汽车之家 API 爬取
└── frontend/
    └── app/
        └── report-studio/          # 分析主页面
```

## 设计说明

**为什么用汽车之家而不是小红书**

小红书无公开 API，反爬机制强，难以稳定获取结构化数据。汽车之家口碑区提供 JSON API，每条评论自带 `scoreList`（用户对各维度的 1-5 分评分），无需 NLP 情感推断即可获得结构化评分，数据质量更可靠。实际业务中，口碑数据与小红书内容高度相关——汽车用户在两个平台的关注点一致，均是购车决策和使用体验。

**评分机制**

维度评分直接取自汽车之家口碑 API 的 `scoreList` 字段（用户手动打分，1-5 整数），系统计算均值、正面率（≥4分）、负面率（≤2分）。评分的绝对值参考意义有限（车主普遍打高分），更有价值的是品牌间相对差距和负面率对比。

**SSE 流式推送**

分析耗时 60-90 秒，使用 `FastAPI StreamingResponse` + `asyncio.Queue` 实现服务端推送，前端通过 `fetch` + `ReadableStream` 消费事件流，实时展示各节点进度。

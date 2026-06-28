"use client";
import { useEffect, useState } from "react";
import { Download, Loader2, Play, ChevronDown, CheckCircle2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/lib/api";

// 零跑车型预设竞品组合
const PRESET_COMPETITORS: Record<string, string[]> = {
  "零跑D19": ["理想L9", "蔚来ES6", "深蓝S07"],
  "零跑C10": ["银河E5", "银河L7", "深蓝S05", "尚界H5"],
  "零跑C11": ["深蓝S05", "深蓝S07", "尚界H5", "元PLUS"],
  "零跑C16": ["银河M9", "理想L6", "eπ008", "唐"],
};

const PRESET_MODELS = Object.keys(PRESET_COMPETITORS);

export default function ReportStudioPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>();
  const [targetBrand, setTargetBrand] = useState("零跑D19");
  const [competitors, setCompetitors] = useState(PRESET_COMPETITORS["零跑D19"].join(","));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progressMessages, setProgressMessages] = useState<string[]>([]);

  useEffect(() => {
    api.scrapeReports().then(setReports).catch(console.error);
  }, []);

  function handleModelSelect(model: string) {
    setTargetBrand(model);
    if (PRESET_COMPETITORS[model]) {
      setCompetitors(PRESET_COMPETITORS[model].join(","));
    }
  }

  async function runAnalysis() {
    setLoading(true);
    setError("");
    setProgressMessages([]);
    try {
      const stream = api.scrapeAndAnalyzeStream({
        target_brand: targetBrand,
        competitor_brands: competitors.split(",").map(s => s.trim()).filter(Boolean),
        max_pages: 5,
      });
      for await (const event of stream) {
        if (event.done) {
          if (event.error) {
            setError(event.error);
          } else {
            setCurrent(event.result);
            const updated = await api.scrapeReports();
            setReports(updated);
          }
        } else {
          setProgressMessages(prev => [...prev, event.message]);
        }
      }
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
        <p className="text-sm text-muted">选择目标车型，自动填入预设竞品，生成竞品口碑情报报告。</p>
      </div>

      {/* 输入区 */}
      <div className="card p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium block mb-1">目标车型</label>
            <div className="relative">
              <select
                className="w-full rounded-md border border-line px-3 py-2 text-sm appearance-none bg-white pr-8"
                value={PRESET_MODELS.includes(targetBrand) ? targetBrand : "custom"}
                onChange={e => {
                  if (e.target.value !== "custom") handleModelSelect(e.target.value);
                }}
              >
                {PRESET_MODELS.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
                <option value="custom">自定义...</option>
              </select>
              <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
            </div>
            {!PRESET_MODELS.includes(targetBrand) && (
              <input
                className="w-full rounded-md border border-line px-3 py-2 text-sm mt-2"
                value={targetBrand}
                onChange={e => setTargetBrand(e.target.value)}
                placeholder="输入车型名称"
              />
            )}
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">竞品车型</label>
            <input
              className="w-full rounded-md border border-line px-3 py-2 text-sm"
              value={competitors}
              onChange={e => setCompetitors(e.target.value)}
              placeholder="逗号分隔，选择预设车型自动填入"
            />
            <p className="text-xs text-muted mt-1">选择上方预设车型后自动填入，也可手动修改</p>
          </div>
        </div>
        <button
          className="btn flex items-center gap-2"
          onClick={runAnalysis}
          disabled={loading}
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          {loading ? "分析中..." : "开始分析"}
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
                className={`w-full rounded-md border p-3 text-left text-sm hover:bg-slate-50 transition-colors ${current?.run_id === r.run_id ? "border-blue-400 bg-blue-50" : "border-line"}`}
                onClick={() => setCurrent(r)}
              >
                <div className="font-medium truncate">{r.user_task}</div>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${r.status === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {r.status}
                  </span>
                  <span className="text-xs text-muted">{r.created_at?.slice(0, 10)}</span>
                </div>
              </button>
            ))}
            {reports.length === 0 && <p className="text-xs text-muted">暂无历史记录</p>}
          </div>
        </aside>

        <section className="space-y-3">
          {current && !loading && (
            <>
              <div className="flex gap-2">
                <button className="btn flex items-center gap-1.5" onClick={exportMarkdown}>
                  <Download size={15} />导出 .md
                </button>
              </div>
              <div className="card p-6 markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {current.report_markdown || current.final_output || "报告内容为空"}
                </ReactMarkdown>
              </div>
            </>
          )}
          {!current && !loading && (
            <div className="card p-10 text-center text-muted text-sm">
              在左侧选择历史报告，或选择车型后点击「开始分析」
            </div>
          )}
          {loading && (
            <div className="card p-8 space-y-4">
              <div className="flex items-center gap-3">
                <Loader2 size={20} className="animate-spin text-blue-500 shrink-0" />
                <span className="text-sm font-medium">正在分析中，预计 60-90 秒...</span>
              </div>
              <div className="space-y-2 pl-8">
                {progressMessages.map((msg, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 size={14} className="text-green-500 shrink-0" />
                    <span className={i === progressMessages.length - 1 ? "text-ink" : "text-muted"}>{msg}</span>
                  </div>
                ))}
                {progressMessages.length === 0 && (
                  <p className="text-sm text-muted">启动分析流程...</p>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

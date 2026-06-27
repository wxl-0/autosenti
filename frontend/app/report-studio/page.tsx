"use client";
import { useEffect, useState } from "react";
import { Download, Loader2, Play } from "lucide-react";
import { api } from "@/lib/api";

export default function ReportStudioPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>();
  const [targetBrand, setTargetBrand] = useState("零跑D19");
  const [competitors, setCompetitors] = useState("理想L9,蔚来ES6,深蓝S07");
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

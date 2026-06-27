"use client";
import { useState } from "react";
import { Play, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { AgentTimeline } from "@/components/agent/agent-timeline";
import { ReviewerPanel } from "@/components/agent/reviewer-panel";
import { ToolCallPanel } from "@/components/agent/tool-call-panel";

export default function AgentConsolePage() {
  const [task, setTask] = useState("基于已上传数据分析用户反馈并生成 Top 机会点和 PRD");
  const [steps, setSteps] = useState<any[]>([]);
  const [result, setResult] = useState<any>();
  const [busy, setBusy] = useState(false);
  async function run() { setBusy(true); try { const r = await api.runAgent(task); setResult(r); setSteps(await api.steps(r.run_id)); } finally { setBusy(false); } }
  return <div className="space-y-5"><div><h1 className="text-2xl font-semibold">Agent Console</h1><p className="text-sm text-muted">AutoSenti Agent 执行日志 — 每个节点的决策与数据追踪。</p></div><section className="card p-4"><div className="flex gap-3"><input className="input flex-1" value={task} onChange={e => setTask(e.target.value)} /><button className="btn btn-primary" disabled={busy} onClick={run}><Play size={15} />运行</button></div></section><div className="grid grid-cols-[1fr_360px] gap-4"><section className="space-y-4"><AgentTimeline steps={steps} /><ReviewerPanel data={result?.reviewer_result} />{result?.final_output && <div className="card p-4"><h2 className="font-semibold">最终输出</h2><p className="mt-2 text-sm">{result.final_output}</p><button className="btn mt-3"><ShieldCheck size={15} />Human-in-the-loop 确认</button></div>}</section><ToolCallPanel step={steps[steps.length - 1]} /></div></div>;
}

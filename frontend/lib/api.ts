const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  createConversation: (title?: string) => request<any>("/api/conversations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) }),
  conversations: () => request<any[]>("/api/conversations"),
  conversation: (id: string) => request<any>(`/api/conversations/${id}`),
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
};

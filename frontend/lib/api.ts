const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function* streamRequest(path: string, body: object): AsyncGenerator<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await res.text());

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith("data: ")) {
        yield JSON.parse(line.slice(6));
      }
    }
  }
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
    body: JSON.stringify({ max_pages: 5, conversation_id: "legacy", ...payload }),
  }),
  scrapeAndAnalyzeStream: (payload: {
    target_brand: string;
    competitor_brands: string[];
    max_pages?: number;
    conversation_id?: string;
  }) => streamRequest("/api/scrape/stream", { max_pages: 5, conversation_id: "legacy", ...payload }),
  scrapeReports: () => request<any[]>("/api/scrape/reports"),
};

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type JobStatus =
  | "pending"
  | "cloning"
  | "parsing"
  | "ingesting"
  | "ready"
  | "error";

export interface RepoStatus {
  id: string;
  slug?: string | null;
  status: JobStatus;
  error?: string | null;
  stats?: Record<string, number>;
}

export async function ingestRepo(url: string): Promise<RepoStatus> {
  const r = await fetch(`${API_BASE}/api/repos`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getRepo(id: string): Promise<RepoStatus> {
  const r = await fetch(`${API_BASE}/api/repos/${id}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export interface Overview {
  summary: string;
  stack: string[];
  entry_points: { path: string; why: string }[];
  key_modules: { path: string; role: string }[];
  mermaid: string;
  first_questions: string[];
}

export async function getOverview(id: string): Promise<Overview> {
  const r = await fetch(`${API_BASE}/api/repos/${id}/overview`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/**
 * Stream a Q&A answer via Server-Sent Events.
 * The backend emits "chunk", "done", "error" events.
 */
export async function streamAsk(
  id: string,
  question: string,
  onChunk: (text: string) => void,
  onError?: (msg: string) => void
): Promise<void> {
  const r = await fetch(`${API_BASE}/api/repos/${id}/ask`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ question }),
  });
  if (!r.ok || !r.body) {
    onError?.(await r.text());
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let currentEvent = "chunk";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE messages are separated by blank lines
    const messages = buf.split("\n\n");
    buf = messages.pop() ?? "";

    for (const msg of messages) {
      const lines = msg.split("\n");
      let data = "";
      for (const ln of lines) {
        if (ln.startsWith("event:")) currentEvent = ln.slice(6).trim();
        else if (ln.startsWith("data:")) data += ln.slice(5).replace(/^ /, "");
      }
      if (currentEvent === "chunk") onChunk(data);
      else if (currentEvent === "error") onError?.(data);
      else if (currentEvent === "done") return;
    }
  }
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ingestRepo } from "@/lib/api";

const EXAMPLES = [
  "https://github.com/pallets/flask",
  "https://github.com/tiangolo/fastapi",
  "https://github.com/vercel/next.js",
];

export default function RepoForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(u: string) {
    setLoading(true);
    setErr(null);
    try {
      const res = await ingestRepo(u);
      router.push(`/repos/${res.id}`);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-2xl">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(url);
        }}
        className="flex gap-2"
      >
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          className="flex-1 rounded-md border border-border bg-panel px-4 py-3 text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !url}
          className="rounded-md bg-accent px-5 py-3 font-medium text-bg hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Working…" : "Explain"}
        </button>
      </form>

      {err && (
        <p className="mt-3 rounded-md border border-err/40 bg-err/10 px-3 py-2 text-sm text-err">
          {err}
        </p>
      )}

      <div className="mt-6 text-sm text-muted">
        <p className="mb-2">Or try one of these:</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((e) => (
            <button
              key={e}
              onClick={() => submit(e)}
              disabled={loading}
              className="rounded-md border border-border bg-panel px-3 py-1.5 font-mono text-xs hover:border-accent disabled:opacity-50"
            >
              {e.replace("https://github.com/", "")}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

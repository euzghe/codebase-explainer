"use client";

import { useEffect, useRef, useState } from "react";

let mermaidPromise: Promise<any> | null = null;
function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((m) => {
      m.default.initialize({
        startOnLoad: false,
        theme: "dark",
        themeVariables: {
          background: "#13171c",
          primaryColor: "#1a2030",
          primaryTextColor: "#e7ebf0",
          primaryBorderColor: "#7c9cf1",
          lineColor: "#8a93a0",
        },
      });
      return m.default;
    });
  }
  return mermaidPromise;
}

export default function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadMermaid().then(async (mermaid) => {
      if (!ref.current || cancelled) return;
      try {
        const id = "mermaid-" + Math.random().toString(36).slice(2, 9);
        const { svg } = await mermaid.render(id, chart);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
        }
      } catch (e: any) {
        setErr(e?.message ?? String(e));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-panel p-4">
      {err ? (
        <pre className="text-xs text-err">{err}</pre>
      ) : (
        <div ref={ref} />
      )}
    </div>
  );
}

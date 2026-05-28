"use client";

import Mermaid from "./Mermaid";
import type { Overview } from "@/lib/api";

export default function OverviewPanel({ data }: { data: Overview }) {
  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-accent">
          Summary
        </h2>
        <p className="leading-relaxed text-ink/90">{data.summary}</p>
      </section>

      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-accent">
          Stack
        </h2>
        <div className="flex flex-wrap gap-2">
          {data.stack.map((s) => (
            <span
              key={s}
              className="rounded-md border border-border bg-panel px-2 py-1 font-mono text-xs"
            >
              {s}
            </span>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wider text-accent">
          Architecture
        </h2>
        <Mermaid chart={data.mermaid} />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <Bucket title="Entry points" items={data.entry_points} k="why" />
        <Bucket title="Key modules" items={data.key_modules} k="role" />
      </section>
    </div>
  );
}

function Bucket({
  title,
  items,
  k,
}: {
  title: string;
  items: { path: string; [k: string]: string }[];
  k: string;
}) {
  return (
    <div>
      <h3 className="mb-2 text-xs uppercase tracking-wider text-accent">
        {title}
      </h3>
      <ul className="space-y-2">
        {items.map((it) => (
          <li
            key={it.path}
            className="rounded-md border border-border bg-panel p-3"
          >
            <div className="font-mono text-xs text-ink">{it.path}</div>
            <div className="mt-1 text-sm text-muted">{it[k]}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

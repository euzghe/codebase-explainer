"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import OverviewPanel from "@/components/Overview";
import Chat from "@/components/Chat";
import { getOverview, getRepo, type JobStatus, type Overview, type RepoStatus } from "@/lib/api";

const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "Queued",
  cloning: "Cloning repo…",
  parsing: "Parsing source files…",
  ingesting: "Writing graph to Neo4j…",
  ready: "Ready",
  error: "Error",
};

export default function RepoPage() {
  const params = useParams<{ id: string }>();
  const repoId = params.id;

  const [status, setStatus] = useState<RepoStatus | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Poll status
  useEffect(() => {
    let stop = false;
    let timer: any;
    async function tick() {
      try {
        const s = await getRepo(repoId);
        if (stop) return;
        setStatus(s);
        if (s.status === "ready") return;
        if (s.status === "error") return;
        timer = setTimeout(tick, 1500);
      } catch (e: any) {
        if (!stop) {
          setErr(e?.message ?? String(e));
          timer = setTimeout(tick, 3000);
        }
      }
    }
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [repoId]);

  // Fetch overview when ready
  useEffect(() => {
    if (status?.status !== "ready" || overview || loadingOverview) return;
    setLoadingOverview(true);
    getOverview(repoId)
      .then(setOverview)
      .catch((e) => setErr(e?.message ?? String(e)))
      .finally(() => setLoadingOverview(false));
  }, [status, repoId, overview, loadingOverview]);

  const ready = status?.status === "ready";

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header className="mb-8">
        <a href="/" className="text-sm text-muted hover:text-ink">
          ← New repo
        </a>
        <h1 className="mt-2 font-mono text-2xl">
          {status?.slug ?? repoId}
        </h1>
        <StatusBadge status={status?.status} stats={status?.stats} />
        {err && (
          <p className="mt-3 rounded-md border border-err/40 bg-err/10 px-3 py-2 text-sm text-err">
            {err}
          </p>
        )}
        {status?.status === "error" && status.error && (
          <p className="mt-3 rounded-md border border-err/40 bg-err/10 px-3 py-2 text-sm text-err">
            {status.error}
          </p>
        )}
      </header>

      {ready ? (
        <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
          <div>
            {overview ? (
              <OverviewPanel data={overview} />
            ) : (
              <div className="rounded-lg border border-border bg-panel p-6 text-muted">
                Generating architecture overview…
              </div>
            )}
          </div>
          <div className="h-[70vh] lg:sticky lg:top-6">
            <Chat
              repoId={repoId}
              starters={
                overview?.first_questions ?? [
                  "What does this codebase do?",
                  "Where is the entry point?",
                  "How is the project organized?",
                  "Where would I add a new feature?",
                ]
              }
            />
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-panel p-8 text-center text-muted">
          {STATUS_LABEL[status?.status ?? "pending"]}
        </div>
      )}
    </main>
  );
}

function StatusBadge({
  status,
  stats,
}: {
  status?: JobStatus;
  stats?: Record<string, number>;
}) {
  if (!status) return null;
  const color =
    status === "ready" ? "ok" : status === "error" ? "err" : "warn";
  return (
    <div className="mt-3 flex items-center gap-3 text-sm">
      <span className={`rounded-full bg-${color}/15 px-2 py-0.5 text-${color}`}>
        {STATUS_LABEL[status]}
      </span>
      {stats && (
        <span className="text-muted">
          {stats.files} files · {stats.symbols} symbols
        </span>
      )}
    </div>
  );
}

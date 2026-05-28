import RepoForm from "@/components/RepoForm";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-2xl">
        <header className="mb-10">
          <h1 className="text-4xl font-semibold tracking-tight">
            Codebase Explainer
          </h1>
          <p className="mt-3 text-muted">
            Paste any GitHub repo. Get a graph-grounded architecture overview
            and a chat that answers <span className="font-mono">where is auth</span>{" "}
            or <span className="font-mono">how would I add a new endpoint</span> with
            file:line citations.
          </p>
        </header>

        <RepoForm />

        <section className="mt-16 grid grid-cols-3 gap-4 text-xs text-muted">
          <Card label="1. Parse">
            We clone, AST-parse with tree-sitter, and write a File→Symbol→Call
            graph into Neo4j.
          </Card>
          <Card label="2. Map">
            An overview agent reads the graph and emits a Mermaid map of the
            project's key modules.
          </Card>
          <Card label="3. Chat">
            Q&amp;A retrieves relevant subgraphs, then Claude answers with
            cached repo context (~0.1× cost per follow-up).
          </Card>
        </section>
      </div>
    </main>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <div className="mb-2 text-[10px] uppercase tracking-wider text-accent">
        {label}
      </div>
      <p className="text-ink/80">{children}</p>
    </div>
  );
}

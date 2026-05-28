"use client";

import { useEffect, useRef, useState } from "react";
import { streamAsk } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function Chat({
  repoId,
  starters,
}: {
  repoId: string;
  starters: string[];
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  async function send(question: string) {
    if (!question.trim() || streaming) return;
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", text: question },
      { role: "assistant", text: "" },
    ]);
    setStreaming(true);

    await streamAsk(
      repoId,
      question,
      (chunk) => {
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = {
            role: "assistant",
            text: copy[copy.length - 1].text + chunk,
          };
          return copy;
        });
      },
      (errMsg) => {
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = {
            role: "assistant",
            text: copy[copy.length - 1].text + `\n\n[error: ${errMsg}]`,
          };
          return copy;
        });
      }
    );

    setStreaming(false);
  }

  return (
    <div className="flex h-full flex-col rounded-lg border border-border bg-panel">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div>
            <p className="mb-3 text-xs uppercase tracking-wider text-accent">
              Suggested questions
            </p>
            <div className="space-y-2">
              {starters.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="w-full rounded-md border border-border bg-bg p-3 text-left text-sm hover:border-accent"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => <Bubble key={i} m={m} />)
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-border p-3"
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this codebase…"
            disabled={streaming}
            className="flex-1 rounded-md border border-border bg-bg px-3 py-2 placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="rounded-md bg-accent px-4 py-2 font-medium text-bg disabled:opacity-50"
          >
            {streaming ? "…" : "Ask"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Bubble({ m }: { m: Message }) {
  return (
    <div className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm " +
          (m.role === "user"
            ? "bg-accent text-bg"
            : "border border-border bg-bg text-ink")
        }
      >
        {m.text || (m.role === "assistant" && <span className="text-muted">…</span>)}
      </div>
    </div>
  );
}

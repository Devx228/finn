"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { type CommandCatalog, type CommandResponse, localCommand } from "@/lib/command";
import { loadWithFallback, postJson } from "@/lib/api";
import { formatAsOf } from "@/lib/format";

const EXAMPLES = [
  "CREDITACC",
  "Who do I know at HDFC Bank?",
  "Show TITAN's 7-day brief",
  "Show CREDITACC promises and who can help",
];

type ApiError = { detail?: { message?: string } };

export function CommandBar() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<CommandCatalog>({ companies: [] });
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CommandResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadWithFallback<CommandCatalog>("/api/command/catalog", "command_catalog.json")
      .then((loaded) => live && setCatalog(loaded.data))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  const run = async (value = query) => {
    const q = value.trim();
    if (!q || busy) return;
    setQuery(q);
    setOpen(true);
    setError(null);
    setResult(null);
    const local = localCommand(q, catalog.companies);
    if (local) {
      setOpen(false);
      setQuery("");
      router.push(local.href);
      return;
    }
    setBusy(true);
    try {
      const response = await postJson<CommandResponse | ApiError>("/api/command", { prompt: q }, { timeoutMs: 45_000 });
      if (!response.ok) {
        const message = (response.data as ApiError).detail?.message;
        setError(message ?? "FINN couldn't route that command.");
      } else {
        setResult(response.data as CommandResponse);
      }
    } catch {
      setError("The live command service is unavailable. Symbols and People searches still work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative border-b border-line px-3 py-2">
      {open && (
        <div className="absolute inset-x-0 bottom-full max-h-[68dvh] overflow-y-auto border-y border-line bg-bg p-3 shadow-2xl">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-[12px] font-semibold uppercase tracking-wider text-ink-3">Ask or go</p>
            <button onClick={() => setOpen(false)} className="min-h-9 px-2 text-[13px] text-ink-2">
              Close
            </button>
          </div>
          <div className="mb-3 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none]">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                onClick={() => void run(example)}
                disabled={busy}
                className="min-h-8 shrink-0 rounded-full border border-line px-3 text-[12px] text-ink-2 disabled:opacity-50"
              >
                {example}
              </button>
            ))}
          </div>
          {!result && !error && !busy && (
            <p className="rounded-md border border-line bg-surface px-3 py-2 text-[12px] leading-snug text-ink-3">
              Symbols, company names and People searches route without a model. Other commands use a model only to choose stored tools.
            </p>
          )}
          {busy && <p className="rounded-md border border-line bg-surface px-3 py-3 text-[13px] text-ink-2">Choosing stored tools…</p>}
          {error && <p className="rounded-md border border-down/30 bg-surface px-3 py-3 text-[13px] text-down">{error}</p>}
          {result && <CommandBlocks result={result} />}
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
        className="flex gap-2"
      >
        <label htmlFor="finn-command" className="sr-only">
          Ask FINN or open a company
        </label>
        <input
          id="finn-command"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ask FINN or open a company…"
          className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-[14px] placeholder:text-ink-3"
        />
        <button disabled={busy || !query.trim()} className="h-10 rounded-lg bg-ink px-3 text-[13px] font-semibold text-bg disabled:opacity-40">
          Go
        </button>
      </form>
    </div>
  );
}

function CommandBlocks({ result }: { result: CommandResponse }) {
  return (
    <div className="space-y-2">
      {result.blocks.map((block, index) => (
        <section key={`${block.type}-${index}`} className="rounded-lg border border-line bg-surface px-3 py-2.5">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-[14px] font-semibold">{block.title}</h2>
            <span className="text-[10px] uppercase tracking-wide text-ink-3">{block.type.replaceAll("_", " ")}</span>
          </div>
          {block.subtitle && (
            <p className="text-[11px] text-ink-3">
              {block.subtitle.startsWith("As of ") ? `As of ${formatAsOf(block.subtitle.slice(6))}` : block.subtitle}
            </p>
          )}
          <ul className="mt-1.5 divide-y divide-line">
            {block.items.map((item, itemIndex) => (
              <li key={`${item.label}-${itemIndex}`} className="py-2 first:pt-1 last:pb-1">
                {item.href ? (
                  <a href={item.href} target={item.href.startsWith("/") ? undefined : "_blank"} rel="noreferrer" className="block">
                    <span className="text-[12px] font-semibold text-ink">{item.label}</span>
                    <span className="block text-[13px] leading-snug text-ink-2">{item.text}</span>
                  </a>
                ) : (
                  <>
                    <span className="text-[12px] font-semibold text-ink">{item.label}</span>
                    <span className="block text-[13px] leading-snug text-ink-2">{item.text}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
          {block.sources.length > 0 && (
            <p className="mt-1 border-t border-line pt-1.5 text-[10px] leading-snug text-ink-3">
              Sources ·{" "}
              {block.sources.map((source, sourceIndex) => (
                <span key={`${source.label}-${sourceIndex}`}>
                  {sourceIndex > 0 && " · "}
                  {source.url ? (
                    <a href={source.url} target="_blank" rel="noreferrer" className="underline">
                      {source.label}
                    </a>
                  ) : (
                    source.label
                  )}
                </span>
              ))}
            </p>
          )}
        </section>
      ))}
      <p className="text-[11px] text-ink-3">The model chose tools only; code built these blocks from stored data.</p>
    </div>
  );
}

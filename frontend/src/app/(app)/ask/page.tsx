"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Sparkles,
  Send,
  Loader2,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  Clock,
  Layers,
  ArrowRight,
} from "lucide-react";
import { useAskAi, useFeatures, useMe } from "@/hooks/items";
import type { AiAskResponse } from "@/lib/types";
import { btnPrimary } from "@/components/ui";

const SUGGESTIONS = [
  "What customer was double charged on checkout during the card processing spike?",
  "What enterprise customer requested a $15,000 refund due to downtime SLA credit?",
  "Why did Redis connection pool exhaustion occur during nightly batch export?",
  "Which customer reported webhook signature validation mismatch on callback payload?",
];

export default function AskPage() {
  const me = useMe();
  const { data: features } = useFeatures();
  const askAi = useAskAi();

  const [question, setQuestion] = useState("");
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [result, setResult] = useState<AiAskResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  const handleAsk = async (q: string) => {
    if (!q.trim()) return;
    setErrorText(null);
    try {
      const res = await askAi.mutateAsync({
        question: q.trim(),
        team_id: selectedTeamId || undefined,
      });
      setResult(res);
    } catch (err: any) {
      setErrorText(err?.problem?.detail || err?.message || "Failed to retrieve grounded AI answer.");
    }
  };

  const teams = me.data?.teams || [];

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {/* Page Header */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <div className="flex size-9 items-center justify-center rounded-xl bg-signal/15 text-signal font-bold shadow-xs">
            <Sparkles className="size-5" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Ask the History</h1>
        </div>
        <p className="text-sm text-muted">
          Grounded operational knowledge across your team’s incidents, changes, approvals, and post-mortems.
          Authorization is strictly enforced before retrieval; responses include exact citation provenance.
        </p>
      </div>

      {/* Query Composer Box */}
      <div className="rounded-2xl border border-line bg-surface p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <label htmlFor="team-scope" className="text-xs font-semibold uppercase tracking-wider text-muted">
            Authorization Scope
          </label>
          <select
            id="team-scope"
            value={selectedTeamId}
            onChange={(e) => setSelectedTeamId(e.target.value)}
            className="rounded-lg border border-line bg-canvas px-3 py-1.5 text-xs font-medium text-ink focus:outline-none focus:ring-2 focus:ring-signal"
          >
            <option value="">All My Authorized Teams</option>
            {teams.map((t) => (
              <option key={t.team_id} value={t.team_id}>
                {t.team_name || t.team?.name || t.team_id} ({t.role})
              </option>
            ))}
          </select>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleAsk(question);
          }}
          className="space-y-3"
        >
          <div className="relative">
            <textarea
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask anything about previous incidents, refund rules, system failures, or team decisions..."
              className="w-full resize-none rounded-xl border border-line bg-canvas p-4 text-sm text-ink placeholder:text-muted focus:border-signal focus:outline-none focus:ring-2 focus:ring-signal/20"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleAsk(question);
                }
              }}
            />
            <div className="absolute bottom-3 right-3 flex items-center gap-2">
              <button
                type="submit"
                disabled={!question.trim() || askAi.isPending}
                className={`${btnPrimary} flex items-center gap-2 px-4 py-2 text-xs shadow-xs`}
              >
                {askAi.isPending ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    <span>Searching...</span>
                  </>
                ) : (
                  <>
                    <Send className="size-3.5" />
                    <span>Ask AI</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>

        {/* Suggestion Chips */}
        <div className="space-y-1.5 pt-2">
          <p className="text-[11px] font-medium text-muted flex items-center gap-1.5">
            <HelpCircle className="size-3" />
            <span>Sample queries from operational history:</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setQuestion(s);
                  handleAsk(s);
                }}
                className="rounded-lg border border-line/70 bg-canvas/60 px-2.5 py-1 text-xs text-muted hover:border-signal hover:text-ink hover:bg-canvas transition-colors text-left"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {errorText && (
        <div className="flex items-start gap-3 rounded-xl border border-p0/20 bg-p0/10 p-4 text-p0">
          <AlertCircle className="size-5 shrink-0 mt-0.5" />
          <div className="text-xs">
            <p className="font-semibold">Query Execution Error</p>
            <p className="mt-0.5 opacity-90">{errorText}</p>
          </div>
        </div>
      )}

      {/* Answer & Retrieval Results */}
      {result && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
          {/* Main Answer Box */}
          <div className="rounded-2xl border border-line bg-surface p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-line/60 pb-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                <Sparkles className="size-4 text-signal" />
                <span>Synthesized Operational Answer</span>
              </div>
              <div className="flex items-center gap-3 text-[11px] text-muted">
                {result.timings_ms && (
                  <span className="flex items-center gap-1">
                    <Clock className="size-3" />
                    <span>
                      retrieval: {result.timings_ms.retrieval ?? 0}ms
                      {result.timings_ms.llm ? ` · synthesis: ${result.timings_ms.llm}ms` : ""}
                    </span>
                  </span>
                )}
                <span className="inline-flex items-center gap-1 rounded-md bg-ok/10 px-2 py-0.5 font-medium text-ok">
                  <ShieldCheck className="size-3" />
                  <span>Team Verified</span>
                </span>
              </div>
            </div>

            {result.degraded && (
              <div className="rounded-xl border border-p1/30 bg-p1/10 p-3 text-xs text-p1 flex items-center gap-2">
                <AlertCircle className="size-4 shrink-0" />
                <span>
                  LLM provider inactive or offline. Displaying authoritative passages retrieved via vector semantic search.
                </span>
              </div>
            )}

            <div className="prose prose-sm max-w-none text-ink text-sm leading-relaxed">
              {result.answer ? (
                <p className="whitespace-pre-line">{result.answer}</p>
              ) : (
                <p className="text-muted italic">
                  No LLM response generated. Refer to the grounded citation sources below.
                </p>
              )}
            </div>
          </div>

          {/* Citations List */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-1.5">
                <Layers className="size-3.5" />
                <span>Grounded Citations ({result.citations.length})</span>
              </h2>
              <span className="text-[11px] text-muted">
                Retrieved chunks from item summaries, timelines, and resolution logs
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {result.citations.map((c, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-line bg-surface p-4 shadow-2xs hover:border-signal/50 transition-colors flex flex-col justify-between gap-3"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <Link
                        href={`/items/${c.item_key}`}
                        className="inline-flex items-center gap-1 text-xs font-bold text-signal hover:underline"
                      >
                        <span>{c.item_key}</span>
                        <ExternalLink className="size-3" />
                      </Link>
                      <span className="rounded bg-line/60 px-1.5 py-0.5 text-[10px] font-mono text-muted uppercase">
                        {c.kind}
                      </span>
                    </div>
                    <p className="text-xs text-ink/90 line-clamp-3 leading-normal">
                      "{c.snippet}"
                    </p>
                  </div>

                  <div className="border-t border-line/40 pt-2 flex items-center justify-between text-[11px] text-muted">
                    <span className="capitalize">{c.kind.replace("_", " ")}</span>
                    <Link
                      href={`/items/${c.item_key}`}
                      className="inline-flex items-center gap-1 font-medium text-ink hover:text-signal"
                    >
                      <span>Open item</span>
                      <ArrowRight className="size-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

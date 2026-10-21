"use client";
import { useState } from "react";
import Link from "next/link";
import { Sparkles, Send, Loader2, ExternalLink, HelpCircle, AlertCircle } from "lucide-react";
import { useAskAi, useFeatures } from "@/hooks/items";
import type { AiAskResponse } from "@/lib/types";

export function AiAssistantWidget({
  itemKey,
  itemId,
  teamId,
}: {
  itemKey?: string;
  itemId?: string;
  teamId?: string;
}) {
  const { data: features } = useFeatures();
  const askAi = useAskAi();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AiAskResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  // If AI is disabled via config, hide widget
  if (features && !features.ai_enabled) {
    return null;
  }

  const handleAsk = async (qText: string) => {
    if (!qText.trim()) return;
    setErrorText(null);
    try {
      const res = await askAi.mutateAsync({
        question: qText.trim(),
        item_id: itemId || undefined,
        team_id: teamId || undefined,
      });
      setResult(res);
    } catch (e: any) {
      setErrorText(e?.problem?.detail || e?.message || "Could not retrieve AI answer.");
    }
  };

  const sampleQuestions = [
    itemKey ? `What similar issues occurred before ${itemKey}?` : "How were recent payment exceptions handled?",
    "What is the required approval protocol for high-value refunds?",
    "Summarize recurring bottlenecks in current queue",
  ];

  return (
    <div className="rounded-2xl border border-line bg-surface p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-lg bg-signal/10 text-signal">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">Ops AI Assistant</h3>
            <p className="text-[11px] text-muted">Grounded operational knowledge with citations</p>
          </div>
        </div>
        <span className="rounded-full border border-signal/30 bg-signal/5 px-2 py-0.5 text-[10px] font-semibold text-signal">
          Grounded RAG
        </span>
      </div>

      {/* Suggested prompts */}
      {!result && !askAi.isPending && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium text-muted">Suggested questions:</p>
          <div className="flex flex-wrap gap-1.5">
            {sampleQuestions.map((sq, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  setQuestion(sq);
                  handleAsk(sq);
                }}
                className="rounded-lg border border-line bg-canvas/60 px-2.5 py-1 text-xs text-left text-muted hover:text-ink hover:bg-canvas transition-colors"
              >
                {sq}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input box */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleAsk(question);
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about operational policies or history..."
          className="flex-1 rounded-lg border border-line bg-canvas/50 px-3 py-2 text-xs text-ink placeholder:text-muted focus:border-signal focus:outline-none"
        />
        <button
          type="submit"
          disabled={askAi.isPending || !question.trim()}
          className="flex size-8 items-center justify-center rounded-lg bg-signal text-white hover:bg-signal-hover disabled:opacity-50 transition-colors shrink-0"
        >
          {askAi.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
        </button>
      </form>

      {/* Error state */}
      {errorText && (
        <div className="flex items-center gap-2 rounded-lg border border-p0/30 bg-p0/10 p-2.5 text-xs text-p0">
          <AlertCircle className="size-4 shrink-0" />
          <span>{errorText}</span>
        </div>
      )}

      {/* Answer output */}
      {result && (
        <div className="space-y-3 rounded-xl bg-canvas/60 p-3.5 border border-line text-xs animate-in fade-in-0 duration-200">
          <div>
            <span className="font-semibold text-ink block mb-1">Answer:</span>
            <p className="leading-relaxed text-ink whitespace-pre-wrap">
              {result.answer || (result.degraded ? "Direct answer degraded, but relevant sources were found:" : "No direct answer available.")}
            </p>
          </div>

          {/* Validated Citations */}
          {result.citations && result.citations.length > 0 && (
            <div className="pt-2 border-t border-line/60 space-y-1.5">
              <span className="text-[11px] font-semibold text-muted uppercase tracking-wider block">
                Sources & Citations
              </span>
              <div className="flex flex-wrap gap-2">
                {result.citations.map((c) => (
                  <Link
                    key={c.marker}
                    href={c.url}
                    className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-[11px] font-medium text-signal hover:underline"
                  >
                    <span>[{c.marker}]</span>
                    <span>{c.item_key}</span>
                    <ExternalLink className="size-2.5 opacity-60" />
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Timing details */}
          {result.timings_ms && (
            <div className="text-[10px] text-muted pt-1 flex justify-between">
              <span>Verified against operational history</span>
              {result.timings_ms.latency && <span>{result.timings_ms.latency}ms</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

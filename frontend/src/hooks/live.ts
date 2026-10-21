"use client";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { qk, touchItem } from "./items";
/** SSE events are hints, never data: on a hint we refetch via REST, so there is one source of truth and one auth path. */
export function useLiveUpdates(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    const es = new EventSource("/api/v1/stream"); // the browser reconnects automatically
    es.addEventListener("item.changed", (e) => { const d = JSON.parse((e as MessageEvent).data); touchItem(qc, d.key); });
    es.addEventListener("resync", () => qc.invalidateQueries());
    es.addEventListener("notification", () => qc.invalidateQueries({ queryKey: ["notifications"] }));
    return () => es.close();
  }, [enabled, qc]);
}

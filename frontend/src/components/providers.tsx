"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "@/lib/api";
import { ToastProvider } from "./toast";
export function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient({ defaultOptions: { queries: {
    staleTime: 15_000, refetchOnWindowFocus: true,
    retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2, // 4xx are decisions, not glitches
  } } }));
  return <QueryClientProvider client={qc}><ToastProvider>{children}</ToastProvider></QueryClientProvider>;
}

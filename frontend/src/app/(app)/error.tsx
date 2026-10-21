"use client";
import { ErrorState } from "@/components/ui";
export default function AppError({ reset }: { error: Error; reset: () => void }) {
  return <ErrorState text="Something went wrong loading this page." onRetry={reset} />;
}

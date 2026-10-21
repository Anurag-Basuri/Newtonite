"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Lock,
  Mail,
  Loader2,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  AlertTriangle,
  ServerOff,
  RotateCw,
} from "lucide-react";
import { api } from "@/lib/api";
import { explain, type ProcessedError } from "@/lib/errors";

const schema = z.object({
  email: z.string().email("Enter a valid work email address"),
  password: z.string().min(1, "Enter your password"),
});

type FormValues = z.infer<typeof schema>;

export default function Login() {
  const router = useRouter();
  const qc = useQueryClient();
  const [demoRole, setDemoRole] = useState<string | null>(null);
  const [processedError, setProcessedError] = useState<ProcessedError | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const onSubmit = handleSubmit(async (v) => {
    setProcessedError(null);
    try {
      await api("/auth/login", { method: "POST", body: v });
      await qc.invalidateQueries({ queryKey: ["me"] });
      router.replace("/overview");
    } catch (err: unknown) {
      const p = explain(err);
      setProcessedError(p);

      // Map field-specific errors if available
      if (p.fieldErrors) {
        if (p.fieldErrors.email) setError("email", { message: p.fieldErrors.email });
        if (p.fieldErrors.password) setError("password", { message: p.fieldErrors.password });
      }
    }
  });

  const fillDemo = (email: string, roleName: string) => {
    setProcessedError(null);
    setValue("email", email);
    setValue("password", "Password123!");
    setDemoRole(roleName);
  };

  const isServerOffline = processedError?.code === "SERVER_OFFLINE";

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-4 py-12">
      {/* Background radial accent glow */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 size-96 rounded-full bg-signal/15 blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-md space-y-6">
        {/* Brand header */}
        <div className="text-center space-y-2">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-signal text-white font-bold text-lg shadow-lg shadow-signal/25">
            OB
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Opsboard</h1>
          <p className="text-xs text-muted max-w-xs mx-auto">
            High-throughput operational mission control for payment & risk workflows.
          </p>
        </div>

        {/* Login Card */}
        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-2xl border border-line bg-surface p-6 sm:p-8 shadow-xl ring-1 ring-line/50 backdrop-blur-md"
        >
          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
              Work Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 size-4 text-muted" />
              <input
                type="email"
                autoComplete="username"
                placeholder="you@company.com"
                {...register("email")}
                className="w-full rounded-xl border border-line bg-canvas/40 pl-9 pr-3 py-2 text-sm text-ink placeholder:text-muted focus:border-signal focus:outline-none"
              />
            </div>
            {errors.email && (
              <p className="mt-1 text-xs text-p0 font-medium">{errors.email.message}</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1.5">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 size-4 text-muted" />
              <input
                type="password"
                autoComplete="current-password"
                placeholder="••••••••••••"
                {...register("password")}
                className="w-full rounded-xl border border-line bg-canvas/40 pl-9 pr-3 py-2 text-sm text-ink placeholder:text-muted focus:border-signal focus:outline-none"
              />
            </div>
            {errors.password && (
              <p className="mt-1 text-xs text-p0 font-medium">{errors.password.message}</p>
            )}
          </div>

          {/* Processed Intelligent Error Box */}
          {processedError && (
            <div
              role="alert"
              className={`rounded-xl border p-3.5 text-xs transition-all animate-in fade-in-0 duration-200 ${
                isServerOffline
                  ? "border-p0/40 bg-p0/10 text-ink"
                  : processedError.tone === "warn"
                  ? "border-p1/40 bg-p1/10 text-ink"
                  : "border-p0/40 bg-p0/10 text-ink"
              }`}
            >
              <div className="flex items-start gap-2.5">
                {isServerOffline ? (
                  <ServerOff className="size-4 text-p0 shrink-0 mt-0.5" />
                ) : processedError.tone === "warn" ? (
                  <AlertTriangle className="size-4 text-p1 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="size-4 text-p0 shrink-0 mt-0.5" />
                )}

                <div className="flex-1 space-y-1">
                  <p className="font-bold text-ink leading-tight">
                    {processedError.title}
                  </p>
                  <p className="text-ink/90 leading-relaxed">
                    {processedError.message}
                  </p>
                  {processedError.actionHint && (
                    <p className="font-medium text-signal pt-0.5">
                      Hint: {processedError.actionHint}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink py-2.5 text-sm font-semibold text-canvas hover:opacity-90 active:scale-[0.99] disabled:opacity-50 transition-all shadow-sm cursor-pointer"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                <span>Signing in...</span>
              </>
            ) : (
              <>
                <span>Sign in to Opsboard</span>
                <ArrowRight className="size-4" />
              </>
            )}
          </button>

          {/* Quick Demo Credentials Fillers */}
          <div className="pt-4 border-t border-line/60">
            <p className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-2 text-center">
              Quick Demo Logins
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => fillDemo("lead@opsboard.dev", "Team Lead")}
                className="rounded-lg border border-line bg-canvas/50 px-2.5 py-1.5 text-left hover:bg-canvas hover:border-signal/50 transition-colors cursor-pointer"
              >
                <div className="font-semibold text-ink">Priya (Lead)</div>
                <div className="text-[10px] text-muted">Approval authority</div>
              </button>

              <button
                type="button"
                onClick={() => fillDemo("member@opsboard.dev", "Team Member")}
                className="rounded-lg border border-line bg-canvas/50 px-2.5 py-1.5 text-left hover:bg-canvas hover:border-signal/50 transition-colors cursor-pointer"
              >
                <div className="font-semibold text-ink">Marcus (Member)</div>
                <div className="text-[10px] text-muted">Claim & triage</div>
              </button>

              <button
                type="button"
                onClick={() => fillDemo("admin@opsboard.dev", "Org Admin")}
                className="rounded-lg border border-line bg-canvas/50 px-2.5 py-1.5 text-left hover:bg-canvas hover:border-signal/50 transition-colors cursor-pointer"
              >
                <div className="font-semibold text-ink">Alice (Admin)</div>
                <div className="text-[10px] text-muted">Full org access</div>
              </button>

              <button
                type="button"
                onClick={() => fillDemo("viewer@opsboard.dev", "Viewer")}
                className="rounded-lg border border-line bg-canvas/50 px-2.5 py-1.5 text-left hover:bg-canvas hover:border-signal/50 transition-colors cursor-pointer"
              >
                <div className="font-semibold text-ink">Victor (Viewer)</div>
                <div className="text-[10px] text-muted">Read-only audit</div>
              </button>
            </div>
            {demoRole && (
              <p className="mt-2 text-center text-[10px] text-signal font-medium">
                Filled {demoRole} credentials. Click "Sign in to Opsboard" above.
              </p>
            )}
          </div>
        </form>

        {/* Security & compliance reassurance */}
        <div className="flex items-center justify-center gap-2 text-xs text-muted">
          <ShieldCheck className="size-3.5 text-ok" />
          <span>Session cookies secured · Optimistic CAS concurrency</span>
        </div>
      </div>
    </div>
  );
}

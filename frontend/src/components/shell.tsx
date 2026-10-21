"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Layers,
  Search,
  Plus,
  LogOut,
  Shield,
  Sparkles,
  Command,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { useMe } from "@/hooks/items";
import { useLiveUpdates } from "@/hooks/live";
import { Skeleton, btnPrimary } from "./ui";
import { CommandPalette } from "./command-palette";
import { CreateItemDialog } from "./create-item-dialog";
import { NotificationsMenu } from "./notifications-menu";

const NAV = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/items", label: "All work", icon: Layers },
  { href: "/teams", label: "Teams", icon: Users },
  { href: "/ask", label: "Ask History", icon: Sparkles },
];

/** Desktop: sticky side rail with search, actions, user badge. Phone: slim top bar + bottom tab bar. */
export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const me = useMe();

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    if (me.isError) router.replace("/login");
  }, [me.isError, router]);

  // Global shortcuts: Cmd+K / Ctrl+K, "/" to search, "c" to create
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || "").toLowerCase();
      const isInput =
        activeTag === "input" ||
        activeTag === "textarea" ||
        activeTag === "select" ||
        document.activeElement?.getAttribute("contenteditable") === "true";

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      } else if (!isInput && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (e.key === "/") {
          e.preventDefault();
          setPaletteOpen(true);
        } else if (e.key.toLowerCase() === "c") {
          e.preventDefault();
          setCreateOpen(true);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useLiveUpdates(Boolean(me.data));

  if (!me.data) {
    return (
      <div className="mx-auto max-w-4xl space-y-6 p-8">
        <Skeleton className="h-10 w-48 rounded-xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  const signOut = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // Clear cookie anyway
    }
    router.replace("/login");
  };

  const userInitial = me.data.user.name ? me.data.user.name.charAt(0).toUpperCase() : "U";

  return (
    <div className="mx-auto min-h-screen max-w-7xl md:grid md:grid-cols-[16rem_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:ring-signal"
      >
        Skip to content
      </a>

      {/* Mobile Header */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-surface/90 px-4 backdrop-blur-md md:hidden">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-lg bg-signal text-white font-bold text-xs shadow-xs">
            OB
          </div>
          <span className="font-semibold tracking-tight text-ink text-sm">Opsboard</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaletteOpen(true)}
            aria-label="Search"
            className="flex size-9 items-center justify-center rounded-lg border border-line text-muted hover:text-ink hover:bg-canvas"
          >
            <Search className="size-4" />
          </button>
          <button
            onClick={() => setCreateOpen(true)}
            aria-label="Create item"
            className="flex size-9 items-center justify-center rounded-lg bg-ink text-canvas hover:opacity-90"
          >
            <Plus className="size-4" />
          </button>
          <NotificationsMenu />
        </div>
      </header>

      {/* Desktop Sticky Sidebar Rail */}
      <aside className="hidden flex-col gap-6 border-r border-line/60 bg-surface/60 px-5 py-6 backdrop-blur-md md:sticky md:top-0 md:flex md:h-screen">
        {/* Brand header */}
        <div className="flex items-center justify-between">
          <Link href="/overview" className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-xl bg-signal text-white font-bold text-sm shadow-sm">
              OB
            </div>
            <div>
              <p className="text-base font-bold tracking-tight text-ink">Opsboard</p>
              <p className="text-[10px] font-medium text-muted uppercase tracking-wider">
                Mission Control
              </p>
            </div>
          </Link>
          <NotificationsMenu />
        </div>

        {/* Global Quick Actions: Search & Create */}
        <div className="space-y-2">
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex w-full items-center justify-between rounded-xl border border-line bg-canvas/70 px-3 py-2 text-xs text-muted hover:border-signal/50 hover:text-ink hover:bg-canvas transition-colors shadow-2xs"
          >
            <div className="flex items-center gap-2">
              <Search className="size-3.5 text-muted" />
              <span>Search or jump to...</span>
            </div>
            <kbd className="inline-flex items-center gap-0.5 rounded border border-line bg-surface px-1.5 py-0.5 text-[10px] font-mono text-muted">
              ⌘K
            </kbd>
          </button>

          <button
            onClick={() => setCreateOpen(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-3 py-2.5 text-xs font-semibold text-canvas hover:opacity-90 active:scale-[0.99] transition-all shadow-sm"
          >
            <Plus className="size-4" />
            <span>Create work item</span>
          </button>
        </div>

        {/* Navigation list */}
        <nav aria-label="Main" className="flex flex-col gap-1">
          <span className="px-3 text-[11px] font-semibold text-muted uppercase tracking-wider mb-1">
            Queues
          </span>
          {NAV.map((n) => {
            const Icon = n.icon;
            const isCurrent =
              n.href === "/overview"
                ? path === "/overview"
                : path.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={isCurrent ? "page" : undefined}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
                  isCurrent
                    ? "bg-signal/10 text-signal shadow-2xs"
                    : "text-muted hover:bg-canvas hover:text-ink"
                }`}
              >
                <Icon className="size-4 shrink-0" />
                <span>{n.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* User profile footer */}
        <div className="mt-auto border-t border-line/60 pt-4">
          <div className="flex items-center gap-3 rounded-xl p-2 transition-colors hover:bg-canvas">
            <div className="flex size-9 items-center justify-center rounded-xl bg-signal/15 text-signal font-semibold text-sm">
              {userInitial}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-ink leading-tight">
                {me.data.user.name}
              </p>
              <p className="truncate text-[11px] text-muted leading-tight">
                {me.data.teams.map((t) => t.team_name || t.team?.name || t.role).join(", ") ||
                  (me.data.is_org_admin ? "Org Admin" : "Member")}
              </p>
            </div>
            <button
              onClick={signOut}
              title="Sign out"
              className="flex size-8 items-center justify-center rounded-lg text-muted hover:text-p0 hover:bg-p0/10 transition-colors"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content container */}
      <main id="main" className="px-4 pb-28 pt-6 md:px-8 md:pb-12 md:pt-8 min-w-0">
        {children}
      </main>

      {/* Mobile Bottom Thumb Navigation */}
      <nav
        aria-label="Mobile Navigation"
        className="safe-b fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-line bg-surface/90 backdrop-blur-md md:hidden"
      >
        {NAV.map((n) => {
          const Icon = n.icon;
          const isCurrent =
            n.href === "/overview"
              ? path === "/overview"
              : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              aria-current={isCurrent ? "page" : undefined}
              className={`flex min-h-14 flex-col items-center justify-center gap-1 text-xs transition-colors ${
                isCurrent ? "font-semibold text-signal" : "text-muted hover:text-ink"
              }`}
            >
              <Icon className="size-4" />
              <span>{n.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Interactive Modals */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onOpenCreate={() => setCreateOpen(true)}
      />

      <CreateItemDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
      />
    </div>
  );
}

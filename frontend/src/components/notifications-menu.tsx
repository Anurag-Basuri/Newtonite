"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check, CheckCheck, Loader2 } from "lucide-react";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/hooks/items";
import { timeAgo } from "@/lib/format";
import type { Notification } from "@/lib/types";

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const router = useRouter();
  const menuRef = useRef<HTMLDivElement>(null);

  const { data: notifications = [], isLoading } = useNotifications(unreadOnly);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleNotificationClick = async (notif: Notification) => {
    if (!notif.read) {
      markRead.mutate(notif.id);
    }
    if (notif.item_key) {
      setOpen(false);
      router.push(`/items/${notif.item_key}`);
    }
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        aria-label="Notifications"
        aria-expanded={open}
        className="relative flex size-9 items-center justify-center rounded-lg border border-line bg-surface text-muted transition-colors hover:text-ink hover:bg-canvas"
      >
        <Bell className="size-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-signal text-[10px] font-bold text-white shadow-xs">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 z-50 w-80 sm:w-96 rounded-2xl bg-surface p-2 shadow-2xl ring-1 ring-line animate-in fade-in-0 zoom-in-95 duration-100">
          <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-ink">Notifications</span>
              {unreadCount > 0 && (
                <span className="rounded-full bg-signal/10 px-2 py-0.5 text-xs font-semibold text-signal">
                  {unreadCount} unread
                </span>
              )}
            </div>
            {notifications.length > 0 && (
              <button
                onClick={() => markAllRead.mutate()}
                disabled={markAllRead.isPending}
                className="flex items-center gap-1 text-xs text-muted hover:text-ink transition-colors"
              >
                <CheckCheck className="size-3.5" />
                Mark all read
              </button>
            )}
          </div>

          {/* Toggle between unread and all */}
          <div className="flex gap-1 p-1 bg-canvas rounded-lg my-2 mx-1 text-xs">
            <button
              onClick={() => setUnreadOnly(true)}
              className={`flex-1 py-1 text-center font-medium rounded-md transition-colors ${
                unreadOnly ? "bg-surface text-ink shadow-xs" : "text-muted hover:text-ink"
              }`}
            >
              Unread
            </button>
            <button
              onClick={() => setUnreadOnly(false)}
              className={`flex-1 py-1 text-center font-medium rounded-md transition-colors ${
                !unreadOnly ? "bg-surface text-ink shadow-xs" : "text-muted hover:text-ink"
              }`}
            >
              All
            </button>
          </div>

          {/* Notifications List */}
          <div className="max-h-72 overflow-y-auto space-y-1">
            {isLoading ? (
              <div className="flex items-center justify-center py-8 text-muted">
                <Loader2 className="size-5 animate-spin" />
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted">
                <p className="font-medium text-ink">All caught up</p>
                <p className="mt-0.5">No {unreadOnly ? "unread " : ""}notifications right now.</p>
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  onClick={() => handleNotificationClick(n)}
                  className={`flex items-start gap-3 rounded-lg p-2.5 text-left text-xs transition-colors cursor-pointer ${
                    !n.read ? "bg-signal/5 hover:bg-signal/10" : "hover:bg-canvas text-muted"
                  }`}
                >
                  <span
                    className={`mt-1 size-2 rounded-full shrink-0 ${
                      !n.read ? "bg-signal" : "bg-line"
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className={`font-medium ${!n.read ? "text-ink" : "text-muted"}`}>{n.title}</p>
                    <p className="line-clamp-2 mt-0.5 text-muted leading-relaxed">{n.body}</p>
                    <span className="mt-1 block text-[10px] text-muted">{timeAgo(n.created_at)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

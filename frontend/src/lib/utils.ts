import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const DAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h > 1 ? "s" : ""} ago`;
  const days = Math.round(h / 24);
  if (days < 7) return `${days} day${days > 1 ? "s" : ""} ago`;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export type TimeFormat = "12h" | "24h";

/** "14:30" -> "2:30 PM" (12h) or unchanged (24h). */
export function fmtTime(hhmm: string, f: TimeFormat): string {
  const m = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(hhmm);
  if (!m || f === "24h") return hhmm;
  const h = Number(m[1]);
  return `${h % 12 || 12}:${m[2]} ${h >= 12 ? "PM" : "AM"}`;
}

/** Re-format every HH:MM inside a sentence (e.g. server messages like "Wed 11:30–13:30"). */
export function fmtTimesIn(text: string, f: TimeFormat): string {
  return f === "24h" ? text : text.replace(/\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s?[AP]M)/g, (t) => fmtTime(t, f));
}

export function formatDateTime(iso: string | null | undefined, f: TimeFormat = "12h"): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: f === "12h" });
}

export function initials(name: string): string {
  return name
    .replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s+/i, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export const ROLE_LABEL = { ADMIN: "Admin", COORDINATOR: "Coordinator", FACULTY: "Faculty", STUDENT: "Student" } as const;

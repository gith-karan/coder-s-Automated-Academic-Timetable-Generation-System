import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, CheckCircle2, FileEdit, Info, Send, XCircle } from "lucide-react";
import type { Diagnostic, RunStatus, TimetableStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/display";
import { useTimeFormat } from "@/app/preferences";

export function StatCard({ label, value, icon, tone = "brand", hint, to }: {
  label: string; value: ReactNode; icon: ReactNode; tone?: "brand" | "ok" | "warn" | "info" | "gold"; hint?: ReactNode; to?: string;
}) {
  const toneCls = { brand: "bg-brand/10 text-brand", ok: "bg-ok/12 text-ok", warn: "bg-warn/12 text-warn", info: "bg-info/12 text-info", gold: "bg-gold/25 text-[#8a6d22] dark:text-gold" }[tone];
  const body = (
    <div className="flex items-center gap-4 rounded-2xl border border-line bg-surface p-4 shadow-[0_1px_2px_rgba(16,24,40,.04)] transition-shadow hover:shadow-md">
      <div className={cn("grid size-12 shrink-0 place-items-center rounded-xl [&>svg]:size-6", toneCls)}>{icon}</div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted">{label}</p>
        <p className="text-2xl font-semibold tabular-nums leading-tight">{value}</p>
        {hint && <p className="truncate text-[11px] text-muted">{hint}</p>}
      </div>
    </div>
  );
  return to ? <Link to={to} className="block focus-visible:outline-2 focus-visible:outline-brand rounded-2xl">{body}</Link> : body;
}

/** Accessible SVG donut (values in %). Colours come from theme tokens. */
export function Donut({ segments, center, sub }: { segments: { label: string; value: number; color: string }[]; center: ReactNode; sub?: string }) {
  const r = 52, c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 140 140" className="size-40 -rotate-90" role="img" aria-label={segments.map((s) => `${s.label} ${s.value}%`).join(", ")}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--border)" strokeWidth="16" />
        {segments.map((s) => {
          const len = (Math.max(0, s.value) / 100) * c;
          const el = <circle key={s.label} cx="70" cy="70" r={r} fill="none" stroke={s.color} strokeWidth="16" strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} strokeLinecap="butt" />;
          offset += len;
          return el;
        })}
        <g className="rotate-90 origin-center">
          <text x="70" y="68" textAnchor="middle" className="fill-[var(--text)] text-[22px] font-bold">{center}</text>
          {sub && <text x="70" y="86" textAnchor="middle" className="fill-[var(--muted)] text-[10px]">{sub}</text>}
        </g>
      </svg>
      <ul className="space-y-2 text-sm">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ background: s.color }} />
            <span className="w-24 text-muted">{s.label}</span>
            <span className="font-semibold tabular-nums">{s.value}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TimetableStatusBadge({ status }: { status: TimetableStatus }) {
  const map = {
    DRAFT: { tone: "neutral", icon: <FileEdit className="size-3" />, label: "Draft" },
    IN_REVIEW: { tone: "warn", icon: <Send className="size-3" />, label: "Awaiting approval" },
    PUBLISHED: { tone: "ok", icon: <CheckCircle2 className="size-3" />, label: "Published" },
  } as const;
  const m = map[status];
  return <Badge tone={m.tone} icon={m.icon}>{m.label}</Badge>;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const tone = status === "SUCCESS" ? "ok" : status === "RUNNING" || status === "QUEUED" ? "info" : status === "CANCELLED" ? "neutral" : "bad";
  const label = { SUCCESS: "Success", INFEASIBLE: "Not possible", PRECHECK_FAILED: "Inputs need attention", TIMEOUT: "Timed out", CANCELLED: "Cancelled", FAILED: "Failed", RUNNING: "Running", QUEUED: "Queued" }[status];
  return <Badge tone={tone}>{label}</Badge>;
}

const FIX_PATH: Record<string, string> = {
  faculty: "/faculty", rooms: "/rooms", subjects: "/subjects", programmes: "/programmes", calendar: "/calendar", constraints: "/constraints",
};

/** Plain-English problem list with "Fix →" deep links (used by Generate review + Generation Report). */
export function DiagnosticList({ items, empty }: { items: Diagnostic[]; empty?: ReactNode }) {
  const { tx } = useTimeFormat();
  if (!items.length) return <>{empty}</>;
  return (
    <ul className="divide-y divide-line">
      {items.map((d, i) => {
        const error = d.severity === "ERROR";
        const Icon = error ? XCircle : d.code.startsWith("SUBJECT_SAME_DAY") ? Info : AlertTriangle;
        const path = d.fix ? FIX_PATH[d.fix.page] : undefined;
        return (
          <li key={i} className="flex items-start gap-3 py-3">
            <Icon className={cn("mt-0.5 size-5 shrink-0", error ? "text-bad" : "text-warn")} />
            <div className="min-w-0 flex-1">
              <p className="text-sm">{tx(d.message)}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <Badge tone={error ? "bad" : "warn"}>{error ? "Must fix" : "Warning"}</Badge>
                {d.entities?.slice(0, 3).map((e) => <Badge key={e.type + e.id} tone="neutral">{e.label}</Badge>)}
              </div>
            </div>
            {path && (
              <Link to={`${path}${d.fix?.id ? `?open=${d.fix.id}` : ""}`} className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-brand hover:bg-brand/8">
                Fix <ArrowRight className="size-3.5" />
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}

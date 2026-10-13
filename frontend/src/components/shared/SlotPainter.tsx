import { useEffect, useMemo, useRef, useState } from "react";
import { Ban, Check, Star } from "lucide-react";
import type { Availability, Grid, TimeRange } from "@/lib/types";
import { cn } from "@/lib/utils";

export type SlotState = "available" | "unavailable" | "preferred" | "commitment";
type Key = `${number}:${number}`;
const k = (d: number, p: number): Key => `${d}:${p}`;
const toMin = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

function within(r: TimeRange[] | undefined | null, day: number, s: string, e: string) {
  return (r ?? []).some((x) => x.day === day && toMin(x.start) <= toMin(s) && toMin(e) <= toMin(x.end));
}
function touches(r: TimeRange[] | undefined | null, day: number, s: string, e: string) {
  return (r ?? []).some((x) => x.day === day && toMin(s) < toMin(x.end) && toMin(x.start) < toMin(e));
}

export function availabilityToSlots(grid: Grid, a: Availability): Map<Key, SlotState> {
  const m = new Map<Key, SlotState>();
  for (const d of grid.days)
    for (const p of d.periods) {
      let st: SlotState = a.available == null || within(a.available, d.day, p.start, p.end) ? "available" : "unavailable";
      if (touches(a.unavailable, d.day, p.start, p.end)) st = "unavailable";
      if (touches(a.commitments, d.day, p.start, p.end)) st = "commitment";
      if (st === "available" && within(a.preferred, d.day, p.start, p.end)) st = "preferred";
      m.set(k(d.day, p.index), st);
    }
  return m;
}

/** Merge consecutive painted periods into time ranges (robust to later period-length changes). */
function toRanges(grid: Grid, m: Map<Key, SlotState>, want: SlotState[]): TimeRange[] {
  const out: TimeRange[] = [];
  for (const d of grid.days) {
    let cur: TimeRange | null = null;
    for (const p of d.periods) {
      const on = want.includes(m.get(k(d.day, p.index)) ?? "available");
      if (on && cur && cur.end === p.start) cur.end = p.end;
      else if (on) { cur = { day: d.day, start: p.start, end: p.end }; out.push(cur); }
      else cur = null;
    }
  }
  return out;
}

export function slotsToAvailability(grid: Grid, m: Map<Key, SlotState>, prev: Availability): Availability {
  return {
    available: null,
    unavailable: toRanges(grid, m, ["unavailable"]),
    preferred: toRanges(grid, m, ["preferred"]),
    commitments: prev.commitments ?? [],
  };
}

const STYLE: Record<SlotState, string> = {
  available: "bg-ok/12 border-ok/30 text-ok",
  preferred: "bg-gold/25 border-gold/60 text-[#8a6d22] dark:text-gold",
  unavailable: "bg-bad/10 border-bad/30 text-bad",
  commitment: "bg-info/12 border-info/30 text-info cursor-not-allowed",
};
const ICON = { available: Check, preferred: Star, unavailable: Ban, commitment: Ban };

/** Click-and-drag weekly painter. Reused for faculty availability (3 brushes) and room blocking (2 brushes). */
export function SlotPainter({ grid, value, onChange, brushes = ["available", "preferred", "unavailable"], readOnly }: {
  grid: Grid; value: Map<Key, SlotState>; onChange: (m: Map<Key, SlotState>) => void;
  brushes?: Exclude<SlotState, "commitment">[]; readOnly?: boolean;
}) {
  const [brush, setBrush] = useState<Exclude<SlotState, "commitment">>(brushes[brushes.length - 1]);
  const painting = useRef(false);
  useEffect(() => {
    const up = () => (painting.current = false);
    window.addEventListener("pointerup", up);
    return () => window.removeEventListener("pointerup", up);
  }, []);
  const maxP = Math.max(0, ...grid.days.map((d) => d.periods.length));
  const labels = useMemo(() => grid.days[0]?.periods ?? [], [grid]);

  const paint = (d: number, p: number) => {
    if (readOnly) return;
    const cur = value.get(k(d, p));
    if (cur === "commitment" || cur === brush) return;
    const next = new Map(value);
    next.set(k(d, p), brush);
    onChange(next);
  };

  const counts = useMemo(() => {
    const c = { available: 0, preferred: 0, unavailable: 0, commitment: 0 };
    value.forEach((v) => c[v]++);
    return c;
  }, [value]);

  return (
    <div className="space-y-3">
      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Brush:</span>
          {brushes.map((b) => {
            const I = ICON[b];
            return (
              <button key={b} type="button" aria-pressed={brush === b} onClick={() => setBrush(b)}
                className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium capitalize",
                  STYLE[b], brush === b ? "ring-2 ring-brand/40" : "opacity-70 hover:opacity-100")}>
                <I className="size-3.5" /> {b}
              </button>
            );
          })}
          <span className="ml-auto text-xs text-muted">
            {counts.available + counts.preferred} free · {counts.preferred} preferred · {counts.unavailable + counts.commitment} blocked
          </span>
        </div>
      )}
      <div className="overflow-x-auto scrollbar-thin">
        <div className="grid min-w-[560px] select-none gap-1" style={{ gridTemplateColumns: `76px repeat(${grid.days.length}, minmax(0,1fr))` }}
          onPointerLeave={() => (painting.current = false)}>
          <div />
          {grid.days.map((d) => <div key={d.day} className="pb-1 text-center text-xs font-semibold text-muted">{d.short}</div>)}
          {Array.from({ length: maxP }).map((_, p) => (
            <div key={p} className="contents">
              <div className="flex items-center text-[11px] tabular-nums text-muted">{labels[p] ? `${labels[p].start}–${labels[p].end}` : `P${p + 1}`}</div>
              {grid.days.map((d) => {
                const st = value.get(k(d.day, p));
                if (!st) return <div key={d.day} />;
                const I = ICON[st];
                return (
                  <button key={d.day} type="button" disabled={readOnly}
                    aria-label={`${d.name} ${labels[p]?.start ?? ""}: ${st}`}
                    onPointerDown={(e) => { e.preventDefault(); painting.current = true; paint(d.day, p); }}
                    onPointerEnter={() => painting.current && paint(d.day, p)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), paint(d.day, p))}
                    className={cn("grid h-9 place-items-center rounded-md border text-xs transition-colors", STYLE[st], !readOnly && "hover:brightness-95")}>
                    <I className="size-3.5" />
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-muted">Tip: click and drag across cells to paint several periods at once. Blue cells are fixed commitments.</p>
    </div>
  );
}

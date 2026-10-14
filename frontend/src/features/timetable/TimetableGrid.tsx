import { useMemo, useState } from "react";
import {
  DndContext, DragOverlay, KeyboardSensor, PointerSensor, pointerWithin, useDraggable, useDroppable, useSensor, useSensors,
  type DragEndEvent, type DragStartEvent,
} from "@dnd-kit/core";
import { Ban, Coffee, Lock, Unlock } from "lucide-react";
import type { Entry, Grid, MoveCell } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Tip } from "@/components/ui/overlay";
import { useTimeFormat } from "@/app/preferences";

const ROW_H = 74;
const BREAK_H = 26;

type Row = { kind: "period"; index: number; start: string; end: string } | { kind: "break"; label: string };

function buildRows(grid: Grid, t: (s: string) => string): Row[] {
  const periods = grid.days[0]?.periods ?? [];
  const rows: Row[] = [];
  periods.forEach((p, i) => {
    if (i > 0 && periods[i - 1].end !== p.start) {
      const b = grid.breaks.find((x) => x.start >= periods[i - 1].end && x.end <= p.start);
      rows.push({ kind: "break", label: `${b?.name ?? "Break"} · ${t(periods[i - 1].end)}–${t(p.start)}` });
    }
    rows.push({ kind: "period", index: p.index, start: t(p.start), end: t(p.end) });
  });
  return rows;
}

/** Assign side-by-side lanes to overlapping sessions on the same day (e.g. parallel batch practicals). */
function lanes(entries: Entry[]): Map<string, { lane: number; of: number }> {
  const out = new Map<string, { lane: number; of: number }>();
  const byDay = new Map<number, Entry[]>();
  entries.forEach((e) => e.day != null && byDay.set(e.day, [...(byDay.get(e.day) ?? []), e]));
  for (const list of byDay.values()) {
    list.sort((a, b) => a.start_period! - b.start_period! || b.length - a.length);
    let cluster: Entry[] = [];
    let clusterEnd = -1;
    let active: { end: number; lane: number }[] = [];
    const flush = () => {
      const n = Math.max(1, ...cluster.map((e) => out.get(e.id)!.lane + 1));
      cluster.forEach((e) => out.set(e.id, { lane: out.get(e.id)!.lane, of: n }));
      cluster = [];
      active = [];
    };
    for (const e of list) {
      const s = e.start_period!, end = s + e.length;
      if (s >= clusterEnd && cluster.length) flush();
      active = active.filter((a) => a.end > s);
      let lane = 0;
      while (active.some((a) => a.lane === lane)) lane++;
      active.push({ end, lane });
      out.set(e.id, { lane, of: 1 });
      cluster.push(e);
      clusterEnd = Math.max(clusterEnd, end);
    }
    if (cluster.length) flush();
  }
  return out;
}

function Chip({ e, editable, onToggleLock, onClick, overlay }: {
  e: Entry; editable: boolean; onToggleLock?: (e: Entry) => void; onClick?: (e: Entry) => void; overlay?: boolean;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: e.id, disabled: !editable || e.locked || overlay });
  const faculty = e.faculty.map((f) => f.name.replace(/^Dr\.\s*/, "Dr. ")).join(", ");
  return (
    <div
      ref={overlay ? undefined : setNodeRef}
      {...(overlay ? {} : attributes)}
      {...(overlay ? {} : listeners)}
      onClick={() => onClick?.(e)}
      aria-label={`${e.subject.short_name} (${e.subject.code}) ${e.subject.name}${e.batch ? `, batch ${e.batch.name}` : ""}, ${faculty}, room ${e.room?.code ?? "unassigned"}${e.locked ? ", locked" : ""}`}
      className={cn(
        `chip chip-${e.color} group relative flex h-full flex-col overflow-hidden rounded-lg border pl-2.5 pr-1.5 py-1.5 text-left text-[11px] leading-tight`,
        editable && !e.locked && "cursor-grab active:cursor-grabbing",
        isDragging && "opacity-30",
        overlay && "rotate-1 shadow-2xl ring-2 ring-brand",
        e.subject.kind === "PRACTICAL" && "border-dashed",
      )}
    >
      <span className="chip-bar absolute inset-y-0 left-0 w-1" />
      <span className="flex items-center gap-1">
        <b className="truncate text-[13px] leading-tight">{e.subject.short_name}</b>
        {e.batch && <span className="rounded bg-black/8 px-1 text-[10px] font-semibold dark:bg-white/10">{e.batch.name}</span>}
        {onToggleLock && editable ? (
          <button
            onPointerDown={(ev) => ev.stopPropagation()}
            onClick={(ev) => { ev.stopPropagation(); onToggleLock(e); }}
            aria-label={e.locked ? "Unlock session" : "Lock session"}
            className={cn("ml-auto rounded p-0.5", e.locked ? "opacity-100" : "opacity-0 group-hover:opacity-70 focus:opacity-100")}
          >
            {e.locked ? <Lock className="size-3" /> : <Unlock className="size-3" />}
          </button>
        ) : e.locked ? <Lock className="ml-auto size-3" /> : null}
      </span>
      <span className="truncate text-[10px] font-medium opacity-70">{e.subject.code}</span>
      <span className="truncate opacity-80">{e.room?.code ?? "No room"}</span>
      <span className="truncate opacity-70">{faculty}</span>
    </div>
  );
}

function TimeText({ text }: { text: string }) {
  const { tx } = useTimeFormat();
  return <>{tx(text)}</>;
}

function Cell({ id, row, col, status, reasons }: { id: string; row: number; col: number; status?: MoveCell["status"]; reasons?: string[] }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const tone = status === "ok" ? "bg-ok/10" : status === "warning" ? "bg-warn/12" : status === "blocked" ? "bg-bad/8" : "";
  const cell = (
    <div ref={setNodeRef} style={{ gridRow: row, gridColumn: col }}
      className={cn("relative rounded-lg border border-line/50 transition-colors", tone, isOver && status !== "blocked" && "ring-2 ring-brand", isOver && status === "blocked" && "ring-2 ring-bad")}>
      {status === "blocked" && isOver && <Ban className="absolute right-1 top-1 size-3.5 text-bad" />}
    </div>
  );
  return reasons?.length ? <Tip label={<TimeText text={reasons.join(" · ")} />}>{cell}</Tip> : cell;
}

export interface TimetableGridProps {
  grid: Grid;
  entries: Entry[];
  unassigned?: Entry[];
  editable: boolean;
  loadOptions?: (e: Entry) => Promise<MoveCell[]>;
  onMove?: (e: Entry, day: number, period: number) => void;
  onToggleLock?: (e: Entry) => void;
  onEntryClick?: (e: Entry) => void;
}

export function TimetableGrid({ grid, entries, unassigned = [], editable, loadOptions, onMove, onToggleLock, onEntryClick }: TimetableGridProps) {
  const { t, format } = useTimeFormat();
  const rows = useMemo(() => buildRows(grid, t), [grid, format]); // eslint-disable-line react-hooks/exhaustive-deps
  const rowOf = useMemo(() => {
    const m = new Map<number, number>();
    rows.forEach((r, i) => r.kind === "period" && m.set(r.index, i + 2));
    return m;
  }, [rows]);
  const laneMap = useMemo(() => lanes(entries), [entries]);
  const [active, setActive] = useState<Entry | null>(null);
  const [options, setOptions] = useState<Map<string, MoveCell> | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));
  const all = [...entries, ...unassigned];

  const onDragStart = (ev: DragStartEvent) => {
    const e = all.find((x) => x.id === ev.active.id) ?? null;
    setActive(e);
    setOptions(null);
    if (e && loadOptions) loadOptions(e).then((cells) => setOptions(new Map(cells.map((c) => [`${c.day}:${c.period}`, c])))).catch(() => undefined);
  };
  const onDragEnd = (ev: DragEndEvent) => {
    const e = active;
    setActive(null);
    setOptions(null);
    if (!e || !ev.over) return;
    const [d, p] = String(ev.over.id).split(":").map(Number);
    if (e.day === d && e.start_period === p) return;
    onMove?.(e, d, p);
  };

  const template = `96px repeat(${grid.days.length}, minmax(132px, 1fr))`;
  const rowTemplate = `40px ${rows.map((r) => (r.kind === "period" ? `${ROW_H}px` : `${BREAK_H}px`)).join(" ")}`;

  return (
    <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => { setActive(null); setOptions(null); }}>
      <div className="print-area overflow-x-auto scrollbar-thin">
        <div className="grid min-w-[760px] gap-1" style={{ gridTemplateColumns: template, gridTemplateRows: rowTemplate }}>
          <div className="sticky left-0 z-20 flex items-center bg-surface text-xs font-semibold text-muted" style={{ gridRow: 1, gridColumn: 1 }}>Time</div>
          {grid.days.map((d, ci) => (
            <div key={d.day} style={{ gridRow: 1, gridColumn: ci + 2 }} className="flex items-center justify-center rounded-lg bg-surface-2 text-xs font-semibold">
              <span className="hidden sm:inline">{d.name}</span><span className="sm:hidden">{d.short}</span>
            </div>
          ))}
          {rows.map((r, ri) =>
            r.kind === "break" ? (
              <div key={`b${ri}`} style={{ gridRow: ri + 2, gridColumn: `1 / span ${grid.days.length + 1}` }}
                className="flex items-center justify-center gap-1.5 rounded-md bg-gold/12 text-[11px] font-medium text-[#8a6d22] dark:text-gold">
                <Coffee className="size-3" /> {r.label}
              </div>
            ) : (
              <div key={`p${ri}`} style={{ gridRow: ri + 2, gridColumn: 1 }} className="sticky left-0 z-20 flex flex-col justify-center bg-surface pr-2 text-[11px] tabular-nums text-muted">
                <span className="font-semibold text-ink">P{r.index + 1}</span><span className="whitespace-nowrap">{r.start}</span><span className="whitespace-nowrap opacity-80">– {r.end}</span>
              </div>
            ),
          )}
          {grid.days.map((d, ci) =>
            d.periods.map((p) => {
              const opt = options?.get(`${d.day}:${p.index}`);
              return <Cell key={`${d.day}:${p.index}`} id={`${d.day}:${p.index}`} row={rowOf.get(p.index)!} col={ci + 2}
                status={active ? opt?.status : undefined} reasons={active ? opt?.reasons : undefined} />;
            }),
          )}
          {entries.map((e) => {
            const col = grid.days.findIndex((d) => d.day === e.day) + 2;
            const row = rowOf.get(e.start_period!);
            if (col < 2 || !row) return null;
            const ln = laneMap.get(e.id) ?? { lane: 0, of: 1 };
            return (
              <div key={e.id} className={cn("z-10 p-0.5", active && "pointer-events-none")}
                style={{ gridColumn: col, gridRow: `${row} / span ${e.length}`, width: `${100 / ln.of}%`, marginLeft: `${(ln.lane * 100) / ln.of}%` }}>
                <Chip e={e} editable={editable} onToggleLock={onToggleLock} onClick={onEntryClick} />
              </div>
            );
          })}
        </div>
      </div>

      {unassigned.length > 0 && (
        <div className="no-print mt-4 rounded-xl border border-dashed border-warn/60 bg-warn/5 p-3">
          <p className="mb-2 text-xs font-semibold text-warn">Unassigned sessions ({unassigned.length}) — drag onto the grid to place them</p>
          <div className="flex flex-wrap gap-2">
            {unassigned.map((e) => (
              <div key={e.id} className="h-[68px] w-40"><Chip e={e} editable={editable} onClick={onEntryClick} /></div>
            ))}
          </div>
        </div>
      )}

      <DragOverlay dropAnimation={null}>
        {active ? <div style={{ height: ROW_H * active.length, width: 150 }}><Chip e={active} editable overlay /></div> : null}
      </DragOverlay>
    </DndContext>
  );
}

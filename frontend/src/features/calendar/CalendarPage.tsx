import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Coffee, Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { CalendarData, Grid } from "@/lib/types";
import { cn, DAYS_SHORT } from "@/lib/utils";
import { Button, IconButton } from "@/components/ui/button";
import { Card, PageHeader, Skeleton } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";

type Form = Omit<CalendarData, "grid">;

export default function CalendarPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["calendar"], queryFn: () => api.get<CalendarData>("/calendar") });
  const [form, setForm] = useState<Form | null>(null);
  const [preview, setPreview] = useState<Grid | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  useEffect(() => { if (data) { const { grid, ...rest } = data; setForm(rest); setPreview(grid); } }, [data]);
  const debounced = useDebounced(form, 300);

  // Live preview: the server computes the period grid exactly as the generator will.
  useEffect(() => {
    if (!debounced) return;
    api.post<Grid>("/calendar/preview", debounced).then((g) => { setPreview(g); setPreviewError(null); })
      .catch((e) => setPreviewError(e.message));
  }, [debounced]);

  const save = useMutation({
    mutationFn: (f: Form) => api.put<CalendarData>("/calendar", f),
    onSuccess: () => { toast.success("University timings saved"); void qc.invalidateQueries({ queryKey: ["calendar"] }); },
  });

  if (!form) return <Skeleton className="h-96" />;
  const set = (p: Partial<Form>) => setForm({ ...form, ...p });

  return (
    <>
      <PageHeader title="Academic Calendar" description="University working days, hours, period duration and scheduled breaks"
        actions={<Button icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate(form)} disabled={!!previewError}>Save changes</Button>} />
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Term">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Academic year"><Input value={form.academic_year} onChange={(e) => set({ academic_year: e.target.value })} /></Field>
              <Field label="Term"><Input value={form.term_label} onChange={(e) => set({ term_label: e.target.value })} /></Field>
            </div>
          </Card>
          <Card title="Working days & hours">
            <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Working days">
              {DAYS_SHORT.map((d, i) => {
                const on = form.working_days.includes(i);
                return (
                  <button key={d} type="button" aria-pressed={on}
                    onClick={() => set({ working_days: on ? form.working_days.filter((x) => x !== i) : [...form.working_days, i].sort() })}
                    className={cn("h-9 w-12 rounded-lg border text-sm font-medium transition-colors", on ? "border-brand bg-brand text-white" : "border-line text-muted hover:text-ink")}>
                    {d}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Day starts"><Input type="time" value={form.day_start} onChange={(e) => set({ day_start: e.target.value })} /></Field>
              <Field label="Day ends"><Input type="time" value={form.day_end} onChange={(e) => set({ day_end: e.target.value })} /></Field>
              <Field label="Period (min)"><Input type="number" min={15} max={240} step={5} value={form.period_minutes} onChange={(e) => set({ period_minutes: Number(e.target.value) })} /></Field>
            </div>
          </Card>
          <Card title="Breaks" action={<Button size="sm" variant="ghost" icon={<Plus className="size-4" />}
            onClick={() => set({ breaks: [...form.breaks, { name: "Break", start_time: "13:00", end_time: "13:30", days: null }] })}>Add</Button>}>
            <div className="space-y-2">
              {form.breaks.map((b, i) => (
                <div key={i} className="grid grid-cols-[1fr_96px_96px_auto] items-center gap-2">
                  <Input aria-label="Break name" value={b.name} onChange={(e) => set({ breaks: form.breaks.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
                  <Input aria-label="Break start" type="time" value={b.start_time} onChange={(e) => set({ breaks: form.breaks.map((x, j) => j === i ? { ...x, start_time: e.target.value } : x) })} />
                  <Input aria-label="Break end" type="time" value={b.end_time} onChange={(e) => set({ breaks: form.breaks.map((x, j) => j === i ? { ...x, end_time: e.target.value } : x) })} />
                  <IconButton label="Remove break" size="sm" onClick={() => set({ breaks: form.breaks.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></IconButton>
                </div>
              ))}
              {!form.breaks.length && <p className="text-sm text-muted">No breaks.</p>}
            </div>
          </Card>
        </div>

        <Card className="lg:col-span-3" title="Live preview" description="Exactly the periods the generator will use. Practicals never span a break.">
          {previewError ? <p className="rounded-lg bg-bad/10 p-3 text-sm text-bad">{previewError}</p> : preview && (
            <>
              <div className="mb-4 flex flex-wrap gap-2 text-xs">
                <span className="rounded-lg bg-brand/10 px-2.5 py-1 font-medium text-brand">{preview.periods_per_week} periods / week</span>
                <span className="rounded-lg bg-surface-2 px-2.5 py-1">{preview.days[0]?.periods.length ?? 0} per day</span>
                <span className="rounded-lg bg-surface-2 px-2.5 py-1">Longest block: {preview.longest_block} periods</span>
              </div>
              <div className="space-y-1.5">
                {(preview.days[0]?.periods ?? []).map((p, i, arr) => (
                  <div key={p.index}>
                    {i > 0 && arr[i - 1].end !== p.start && (
                      <div className="my-1.5 flex items-center gap-2 rounded-lg border border-dashed border-gold/60 bg-gold/10 px-3 py-1.5 text-xs text-[#8a6d22] dark:text-gold">
                        <Coffee className="size-3.5" />{preview.breaks.find((b) => b.start >= arr[i - 1].end && b.end <= p.start)?.name ?? "Break"} · {arr[i - 1].end}–{p.start}
                      </div>
                    )}
                    <div className="flex items-center gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm">
                      <Clock className="size-4 text-muted" />
                      <span className="w-20 font-medium">Period {p.index + 1}</span>
                      <span className="tabular-nums text-muted">{p.start} – {p.end}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </>
  );
}

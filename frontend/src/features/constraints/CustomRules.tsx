import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Building2, Clock, Layers, Plus, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useAll } from "@/lib/hooks";
import type { CustomRule, Faculty, Group, Programme, Room, RuleKind, Subject } from "@/lib/types";
import { cn, DAYS, DAYS_SHORT } from "@/lib/utils";
import { Button, IconButton } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/display";
import { Field, Input, Segmented, Select, Switch } from "@/components/ui/form";
import { Modal } from "@/components/ui/overlay";
import { useTimeFormat } from "@/app/preferences";

const TYPES: { kind: RuleKind; title: string; example: string; icon: typeof Ban }[] = [
  { kind: "CLASS_BLOCK", title: "Keep a class free at certain times", example: "e.g. M.Sc. CS has Library / Project on Friday afternoons", icon: Ban },
  { kind: "SUBJECT_WINDOW", title: "Schedule a subject only at certain times", example: "e.g. Physics Lab only in the afternoons", icon: Clock },
  { kind: "FACULTY_MAX_CONSECUTIVE", title: "Limit back-to-back teaching", example: "e.g. no faculty teaches more than 3 periods in a row", icon: Layers },
  { kind: "ROOM_RESERVED", title: "Reserve a room for some programmes", example: "e.g. CSFRL only for M.Tech. AI & DS and M.Sc. DFIS", icon: Building2 },
];
const WEIGHTS = [{ v: 2, l: "Low" }, { v: 5, l: "Medium" }, { v: 9, l: "High" }];

function DayChips({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {[0, 1, 2, 3, 4, 5].map((d) => {
        const on = value.includes(d);
        return (
          <button key={d} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== d) : [...value, d].sort())}
            className={cn("h-8 w-12 rounded-lg border text-xs font-medium", on ? "border-brand bg-brand text-white" : "border-line text-muted")}>
            {DAYS_SHORT[d]}
          </button>
        );
      })}
    </div>
  );
}

export function CustomRules({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient();
  const { t } = useTimeFormat();
  const rules = useAll<CustomRule>("custom-rules");
  const programmes = useAll<Programme>("programmes");
  const groups = useAll<Group>("groups");
  const subjects = useAll<Subject>("subjects");
  const faculty = useAll<Faculty>("faculty");
  const rooms = useAll<Room>("rooms");
  const [kind, setKind] = useState<RuleKind | null>(null);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ programme_id: "", group_id: "", subject_id: "", faculty_id: "", room_id: "", label: "Library / Project",
    days: [4] as number[], start: "14:30", end: "17:30", max: 3, programme_ids: [] as string[], mode: "HARD" as "HARD" | "SOFT", weight: 5 });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["custom-rules"] });
  const save = useMutation({
    mutationFn: (body: unknown) => api.post("/custom-rules", body),
    onSuccess: () => { toast.success("Rule added — it applies to the next generation"); setOpen(false); setKind(null); invalidate(); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save rule"),
    meta: { silent: true },
  });
  const toggle = useMutation({ mutationFn: (r: CustomRule) => api.patch(`/custom-rules/${r.id}`, { enabled: !r.enabled }), onSuccess: invalidate });
  const remove = useMutation({ mutationFn: (id: string) => api.del(`/custom-rules/${id}`), onSuccess: invalidate });

  const name = {
    group: (id: unknown) => groups.data?.find((g) => g.id === id)?.label ?? "a class",
    subject: (id: unknown) => subjects.data?.find((s) => s.id === id)?.code ?? "a subject",
    faculty: (id: unknown) => (id ? faculty.data?.find((x) => x.id === id)?.name ?? "a faculty member" : "Every faculty member"),
    room: (id: unknown) => rooms.data?.find((r) => r.id === id)?.code ?? "a room",
    progs: (ids: unknown) => ((ids as string[]) ?? []).map((id) => programmes.data?.find((p) => p.id === id)?.code ?? "?").join(", "),
  };
  const days = (ds: number[]) => ds.map((d) => DAYS_SHORT[d]).join(", ");
  const sentence = (r: CustomRule) => {
    const p = r.params as Record<string, unknown>;
    switch (r.kind) {
      case "CLASS_BLOCK": {
        const rs = (p.ranges as { day: number; start: string; end: string }[]) ?? [];
        return `${name.group(p.group_id)} is kept free ${days(rs.map((x) => x.day))} ${t(rs[0]?.start ?? "")}–${t(rs[0]?.end ?? "")} (${p.label}).`;
      }
      case "SUBJECT_WINDOW": return `${name.subject(p.subject_id)} is scheduled only on ${days(p.days as number[])}, ${t(String(p.start))}–${t(String(p.end))}.`;
      case "FACULTY_MAX_CONSECUTIVE": return `${name.faculty(p.faculty_id)} teaches at most ${p.max} periods in a row.`;
      case "ROOM_RESERVED": return `${name.room(p.room_id)} is used only by ${name.progs(p.programme_ids)}.`;
    }
  };

  const submit = () => {
    if (!kind) return;
    const base = { kind, mode: f.mode, weight: f.weight, enabled: true };
    const params =
      kind === "CLASS_BLOCK" ? { group_id: f.group_id, label: f.label, ranges: f.days.map((d) => ({ day: d, start: f.start, end: f.end })) }
      : kind === "SUBJECT_WINDOW" ? { subject_id: f.subject_id, days: f.days, start: f.start, end: f.end }
      : kind === "FACULTY_MAX_CONSECUTIVE" ? { faculty_id: f.faculty_id || null, max: f.max }
      : { room_id: f.room_id, programme_ids: f.programme_ids };
    save.mutate({ ...base, params, note: kind === "CLASS_BLOCK" ? f.label : null });
  };
  const ready = kind === "CLASS_BLOCK" ? f.group_id && f.days.length : kind === "SUBJECT_WINDOW" ? f.subject_id && f.days.length
    : kind === "ROOM_RESERVED" ? f.room_id && f.programme_ids.length : kind === "FACULTY_MAX_CONSECUTIVE";
  const classes = groups.data?.filter((g) => !f.programme_id || g.programme_id === f.programme_id) ?? [];
  const subs = subjects.data?.filter((s) => !f.programme_id || s.programme_id === f.programme_id) ?? [];
  const timeFields = (
    <div className="grid grid-cols-2 gap-3">
      <Field label="From"><Input type="time" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
      <Field label="To"><Input type="time" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
    </div>
  );

  return (
    <Card title="Custom rules" description="Your own scheduling rules. Built from safe templates, checked by the generator and the validator."
      action={canEdit && <Button size="sm" variant="outline" icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>Add rule</Button>}>
      <ul className="space-y-2">
        {rules.data?.map((r) => (
          <li key={r.id} className={cn("flex items-center gap-3 rounded-xl border border-line px-3 py-2.5 text-sm", !r.enabled && "opacity-50")}>
            <Wand2 className="size-4 shrink-0 text-brand" />
            <span className="flex-1">{sentence(r)}</span>
            <Badge tone={r.mode === "HARD" ? "bad" : "info"}>{r.mode === "HARD" ? "Must" : "Prefer"}</Badge>
            {canEdit && <>
              <Switch checked={r.enabled} onCheckedChange={() => toggle.mutate(r)} />
              <IconButton label="Delete rule" size="sm" className="hover:text-bad" onClick={() => remove.mutate(r.id)}><Trash2 className="size-4" /></IconButton>
            </>}
          </li>
        ))}
        {rules.data?.length === 0 && <p className="text-sm text-muted">No custom rules yet.</p>}
      </ul>

      <Modal open={open} onOpenChange={(o) => { setOpen(o); if (!o) setKind(null); }} size="lg"
        title={kind ? TYPES.find((t) => t.kind === kind)!.title : "Add a custom rule"}
        description={kind ? undefined : "Choose what kind of rule you need."}
        footer={kind ? <>
          <Button variant="secondary" onClick={() => setKind(null)}>Back</Button>
          <Button loading={save.isPending} disabled={!ready} onClick={submit}>Add rule</Button>
        </> : undefined}>
        {!kind ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {TYPES.map((t) => (
              <button key={t.kind} onClick={() => { setKind(t.kind); setF((x) => ({ ...x, mode: "HARD" })); }}
                className="flex gap-3 rounded-xl border border-line p-4 text-left hover:border-brand/50 hover:bg-surface-2">
                <t.icon className="mt-0.5 size-5 shrink-0 text-brand" />
                <span><b className="block text-sm">{t.title}</b><span className="text-xs text-muted">{t.example}</span></span>
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {(kind === "CLASS_BLOCK" || kind === "SUBJECT_WINDOW") && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="1. Programme"><Select value={f.programme_id} onChange={(e) => setF({ ...f, programme_id: e.target.value, group_id: "", subject_id: "" })}>
                  <option value="">Select…</option>{programmes.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</Select></Field>
                {kind === "CLASS_BLOCK" ? (
                  <Field label="2. Class"><Select value={f.group_id} disabled={!f.programme_id} onChange={(e) => setF({ ...f, group_id: e.target.value })}>
                    <option value="">Select…</option>{classes.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}</Select></Field>
                ) : (
                  <Field label="2. Subject"><Select value={f.subject_id} disabled={!f.programme_id} onChange={(e) => setF({ ...f, subject_id: e.target.value })}>
                    <option value="">Select…</option>{subs.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}</Select></Field>
                )}
              </div>
            )}
            {kind === "CLASS_BLOCK" && <Field label="What is this time for?"><Input value={f.label} maxLength={60} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>}
            {(kind === "CLASS_BLOCK" || kind === "SUBJECT_WINDOW") && <>
              <Field label="Days"><DayChips value={f.days} onChange={(days) => setF({ ...f, days })} /></Field>
              {timeFields}
            </>}
            {kind === "FACULTY_MAX_CONSECUTIVE" && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Faculty"><Select value={f.faculty_id} onChange={(e) => setF({ ...f, faculty_id: e.target.value })}>
                  <option value="">Every faculty member</option>{faculty.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select></Field>
                <Field label="At most this many periods in a row"><Input type="number" min={1} max={8} value={f.max} onChange={(e) => setF({ ...f, max: Number(e.target.value) })} /></Field>
              </div>
            )}
            {kind === "ROOM_RESERVED" && <>
              <Field label="Room"><Select value={f.room_id} onChange={(e) => setF({ ...f, room_id: e.target.value })}>
                <option value="">Select…</option>{rooms.data?.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.name}</option>)}</Select></Field>
              <Field label="Only for these programmes">
                <div className="flex flex-wrap gap-1.5">
                  {programmes.data?.map((p) => {
                    const on = f.programme_ids.includes(p.id);
                    return <button key={p.id} type="button" aria-pressed={on} onClick={() => setF({ ...f, programme_ids: on ? f.programme_ids.filter((x) => x !== p.id) : [...f.programme_ids, p.id] })}
                      className={cn("rounded-full border px-2.5 py-1 text-xs font-medium", on ? "border-brand bg-brand/10 text-brand" : "border-line text-muted")}>{p.code}</button>;
                  })}
                </div>
              </Field>
            </>}
            {(kind === "SUBJECT_WINDOW" || kind === "FACULTY_MAX_CONSECUTIVE") && (
              <div className="flex flex-wrap items-center gap-3">
                <Segmented size="sm" value={f.mode} onChange={(mode) => setF({ ...f, mode })}
                  options={[{ value: "HARD", label: "Must (hard)" }, { value: "SOFT", label: "Prefer (soft)" }]} />
                {f.mode === "SOFT" && <Select className="w-32" value={f.weight} onChange={(e) => setF({ ...f, weight: Number(e.target.value) })}>
                  {WEIGHTS.map((w) => <option key={w.v} value={w.v}>{w.l} importance</option>)}</Select>}
              </div>
            )}
            <p className="text-xs text-muted">
              {kind === "CLASS_BLOCK" ? `The class will never be scheduled on ${f.days.map((d) => DAYS[d]).join(", ") || "…"} between ${t(f.start)} and ${t(f.end)}.`
                : kind === "ROOM_RESERVED" ? "Other programmes will never be placed in this room."
                : f.mode === "HARD" ? "The generator will never break this rule; if it can't be met, the report explains why." : "The generator follows this rule where possible."}
            </p>
          </div>
        )}
      </Modal>
    </Card>
  );
}

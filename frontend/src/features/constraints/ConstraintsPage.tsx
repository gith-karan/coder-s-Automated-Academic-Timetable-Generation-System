import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleOff, Feather, Lock, Pin, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAll, useRemove, useSave } from "@/lib/hooks";
import type { CalendarData, ConstraintItem, Group, Programme, Room, Subject } from "@/lib/types";
import { useAuth } from "@/app/auth";
import { useTimeFormat } from "@/app/preferences";
import { CustomRules } from "./CustomRules";
import { cn, DAYS } from "@/lib/utils";
import { Button, IconButton } from "@/components/ui/button";
import { Card, PageHeader, Skeleton, Tabs } from "@/components/ui/display";
import { Field, Input, Segmented, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/overlay";

const MODE_ICON = { HARD: <Lock className="size-3.5" />, SOFT: <Feather className="size-3.5" />, OFF: <CircleOff className="size-3.5" /> };
const WEIGHTS = [{ v: 2, l: "Low" }, { v: 5, l: "Medium" }, { v: 9, l: "High" }];

interface FixedRow { id: string; subject_id: string; group_id: string; batch_id: string | null; day: number; start_period: number; room_id: string | null; note: string | null }

function FixedSessions({ canEdit }: { canEdit: boolean }) {
  const { t } = useTimeFormat();
  const list = useAll<FixedRow>("fixed-sessions");
  const programmes = useAll<Programme>("programmes");
  const subjects = useAll<Subject>("subjects");
  const groups = useAll<Group>("groups");
  const rooms = useAll<Room>("rooms");
  const cal = useQuery({ queryKey: ["calendar"], queryFn: () => api.get<CalendarData>("/calendar") });
  const save = useSave("fixed-sessions");
  const remove = useRemove("fixed-sessions");
  const [open, setOpen] = useState(false);
  const empty = { programme_id: "", group_id: "", subject_id: "", batch_id: "", day: 0, start_period: 0, room_id: "", note: "" };
  const [f, setF] = useState(empty);
  // Cascade: programme -> class -> subjects of that class's semester -> batch (practicals) -> suitable rooms
  const classes = (groups.data ?? []).filter((g) => g.programme_id === f.programme_id);
  const grp = groups.data?.find((g) => g.id === f.group_id);
  const subs = (subjects.data ?? []).filter((x) => grp && x.programme_id === grp.programme_id && x.semester === grp.semester);
  const subj = subjects.data?.find((x) => x.id === f.subject_id);
  const suitableRooms = (rooms.data ?? []).filter((r) => r.is_active && (!subj ? true
    : subj.kind === "PRACTICAL" ? r.kind === "LAB" && (!subj.lab_type_id || r.lab_type_id === subj.lab_type_id) : true));
  const periods = cal.data?.grid.days.find((d) => d.day === f.day)?.periods ?? cal.data?.grid.days[0]?.periods ?? [];
  const name = (id: string, arr?: { id: string; code?: string; label?: string }[]) => arr?.find((x) => x.id === id)?.code ?? arr?.find((x) => x.id === id)?.label ?? "—";

  return (
    <Card title="Fixed sessions" description="Sessions pinned to a slot by the coordinator. The generator never moves them."
      action={canEdit && <Button size="sm" variant="outline" icon={<Plus className="size-4" />} onClick={() => { setF(empty); setOpen(true); }}>Add</Button>}>
      <ul className="space-y-2">
        {list.data?.map((r) => (
          <li key={r.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2 text-sm">
            <Pin className="size-4 text-brand" />
            <span className="font-medium">{name(r.subject_id, subjects.data)}</span>
            <span className="text-muted">{name(r.group_id, groups.data)}</span>
            <span className="ml-auto text-muted">{DAYS[r.day]} · P{r.start_period + 1}{r.room_id ? ` · ${name(r.room_id, rooms.data)}` : ""}</span>
            {canEdit && <IconButton label="Remove fixed session" size="sm" onClick={() => remove.mutate(r.id)}><Trash2 className="size-4" /></IconButton>}
          </li>
        ))}
        {list.data?.length === 0 && <p className="text-sm text-muted">No fixed sessions.</p>}
      </ul>
      <Modal open={open} onOpenChange={setOpen} title="Add fixed session" description="Pick step by step: programme, class, then subject." footer={<>
        <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
        <Button loading={save.isPending} disabled={!f.subject_id || !f.group_id}
          onClick={() => save.mutate({ body: { subject_id: f.subject_id, group_id: f.group_id, batch_id: f.batch_id || null, day: f.day,
            start_period: f.start_period, room_id: f.room_id || null, note: f.note || null } },
            { onSuccess: () => { toast.success("Fixed session added"); setOpen(false); }, onError: (e) => toast.error(e.message) })}>Add</Button>
      </>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="1. Programme"><Select value={f.programme_id} onChange={(e) => setF({ ...f, programme_id: e.target.value, group_id: "", subject_id: "", batch_id: "" })}>
            <option value="">Select…</option>{programmes.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</Select></Field>
          <Field label="2. Class"><Select value={f.group_id} disabled={!f.programme_id} onChange={(e) => setF({ ...f, group_id: e.target.value, subject_id: "", batch_id: "" })}>
            <option value="">{f.programme_id ? "Select…" : "Choose the programme first"}</option>{classes.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}</Select></Field>
          <Field label="3. Subject" className="col-span-2"><Select value={f.subject_id} disabled={!grp} onChange={(e) => setF({ ...f, subject_id: e.target.value, batch_id: "", room_id: "" })}>
            <option value="">{grp ? "Select…" : "Choose the class first"}</option>{subs.map((x) => <option key={x.id} value={x.id}>{x.code} — {x.name}</option>)}</Select></Field>
          {subj?.kind === "PRACTICAL" && !!grp?.batches.length && (
            <Field label="Batch" className="col-span-2"><Select value={f.batch_id} onChange={(e) => setF({ ...f, batch_id: e.target.value })}>
              <option value="">Select…</option>{grp.batches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></Field>
          )}
          <Field label="4. Day"><Select value={f.day} onChange={(e) => setF({ ...f, day: Number(e.target.value) })}>
            {cal.data?.grid.days.map((d) => <option key={d.day} value={d.day}>{d.name}</option>)}</Select></Field>
          <Field label="5. Starting period"><Select value={f.start_period} onChange={(e) => setF({ ...f, start_period: Number(e.target.value) })}>
            {periods.map((p) => <option key={p.index} value={p.index}>P{p.index + 1} · {t(p.start)}</option>)}</Select></Field>
          <Field label="Room (optional)" className="col-span-2"><Select value={f.room_id} onChange={(e) => setF({ ...f, room_id: e.target.value })}>
            <option value="">Let the generator choose</option>{suitableRooms.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.name} ({r.capacity} seats)</option>)}</Select></Field>
          <Field label="Note" className="col-span-2"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="e.g. Guest lecture series" /></Field>
        </div>
      </Modal>
    </Card>
  );
}

export default function ConstraintsPage() {
  const { can } = useAuth();
  const canEdit = can("setup.edit");
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["constraints"], queryFn: () => api.get<{ mandatory: string[]; configurable: ConstraintItem[] }>("/constraints") });
  const [items, setItems] = useState<ConstraintItem[]>([]);
  const [tab, setTab] = useState("Faculty");
  useEffect(() => { if (data) setItems(data.configurable); }, [data]);
  const save = useMutation({
    mutationFn: () => api.put("/constraints", { items: items.map(({ key, mode, weight, value }) => ({ key, mode, weight, value })) }),
    onSuccess: () => { toast.success("Constraints saved"); void qc.invalidateQueries({ queryKey: ["constraints"] }); },
  });
  const upd = (key: string, p: Partial<ConstraintItem>) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x)));
  const dirty = JSON.stringify(items) !== JSON.stringify(data?.configurable ?? []);

  return (
    <>
      <PageHeader title="Constraints & Rules" description="Mandatory rules are always enforced; preferences are honoured where possible; add your own rules below"
        actions={canEdit && <Button icon={<Save className="size-4" />} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>Save changes</Button>} />
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <Tabs value={tab} onValueChange={setTab} tabs={["Faculty", "Rooms", "Subjects", "Global"].map((t) => ({ value: t, label: t }))} />
            {!data ? <Skeleton className="mt-4 h-40" /> : (
              <fieldset disabled={!canEdit}><ul className="mt-2 divide-y divide-line">
                {items.filter((c) => c.category === tab).map((c) => (
                  <li key={c.key} className="flex flex-wrap items-center gap-4 py-4">
                    <div className="min-w-56 flex-1">
                      <p className="text-sm font-medium">{c.label}</p>
                      <p className="text-xs text-muted">{c.description}</p>
                    </div>
                    {c.has_value && c.mode !== "OFF" && (
                      <Input aria-label={`${c.label} value`} type="number" min={1} max={16} className="w-20" value={c.value ?? ""} onChange={(e) => upd(c.key, { value: Number(e.target.value) })} />
                    )}
                    {c.mode === "SOFT" && (
                      <Select aria-label={`${c.label} importance`} className="w-28" value={WEIGHTS.reduce((a, w) => Math.abs(w.v - c.weight) < Math.abs(a.v - c.weight) ? w : a).v}
                        onChange={(e) => upd(c.key, { weight: Number(e.target.value) })}>
                        {WEIGHTS.map((w) => <option key={w.v} value={w.v}>{w.l}</option>)}
                      </Select>
                    )}
                    <Segmented size="sm" value={c.mode} onChange={(m) => upd(c.key, { mode: m })}
                      options={(["HARD", "SOFT", "OFF"] as const).map((m) => ({ value: m, label: m[0] + m.slice(1).toLowerCase(), icon: MODE_ICON[m], disabled: !c.modes.includes(m) }))} />
                  </li>
                ))}
              </ul></fieldset>
            )}
          </Card>
          <CustomRules canEdit={canEdit} />
          <FixedSessions canEdit={canEdit} />
        </div>

        <div className="space-y-5">
          <Card title="Quick info">
            <ul className="space-y-3 text-sm">
              {[["HARD", "Mandatory — can never be violated", "text-bad bg-bad/10"], ["SOFT", "Preference — met where possible", "text-info bg-info/10"], ["OFF", "Ignored by the generator", "text-muted bg-line/60"]].map(([m, d, cls]) => (
                <li key={m} className="flex items-center gap-3">
                  <span className={cn("grid size-8 place-items-center rounded-lg", cls)}>{MODE_ICON[m as "HARD"]}</span>
                  <span><b className="block text-xs">{m}</b><span className="text-xs text-muted">{d}</span></span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Always enforced" description="From the problem statement — cannot be switched off">
            <ul className="space-y-2">
              {data?.mandatory.map((m) => (
                <li key={m} className="flex gap-2 text-xs"><ShieldCheck className="size-4 shrink-0 text-ok" />{m}</li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

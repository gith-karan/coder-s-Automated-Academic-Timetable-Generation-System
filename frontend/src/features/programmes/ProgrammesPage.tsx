import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GraduationCap, Layers, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useAll, useRemove, useSave } from "@/lib/hooks";
import type { Group, Paged, Programme, Room, UserRow } from "@/lib/types";
import { useAuth } from "@/app/auth";
import { HelpTip } from "@/components/ui/overlay";
import { Button, IconButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { ResourcePage, type ResourceConfig } from "@/components/shared/ResourcePage";

const LEVELS = [
  { value: "UG", label: "Undergraduate" }, { value: "PG", label: "Postgraduate" },
  { value: "INTEGRATED", label: "Integrated" }, { value: "PHD", label: "Ph.D." }, { value: "DIPLOMA", label: "Diploma" },
];
export const SCHOOLS = [
  "School of Cyber Security & Digital Forensics", "School of Forensic Science", "School of Engineering & Technology",
  "School of Behavioural Forensics", "School of Law, Forensic Justice & Policy Studies", "School of Management Studies",
  "School of Pharmacy", "School of Police Science & Security Studies", "School of Medico-Legal Studies",
].map((s) => ({ value: s, label: s }));

const MAX_STRENGTH = 500;

interface DraftGroup {
  id?: string; semester: number; section: string; strength: number | ""; home_room_id: string;
  batches: { name: string; strength: number | "" }[];
}

function problems(d: DraftGroup): string[] {
  const out: string[] = [];
  const s = Number(d.strength);
  if (!Number.isInteger(s) || s < 1 || s > MAX_STRENGTH) out.push(`Number of students must be a whole number from 1 to ${MAX_STRENGTH}.`);
  if (!/^[A-Za-z0-9]{1,8}$/.test(d.section)) out.push("Section must be 1–8 letters or digits (e.g. A).");
  d.batches.forEach((b, i) => {
    const n = Number(b.strength);
    if (!b.name.trim()) out.push(`Batch ${i + 1} needs a name (e.g. B1).`);
    if (!Number.isInteger(n) || n < 1) out.push(`Batch ${b.name || i + 1}: enter at least 1 student.`);
    else if (Number.isInteger(s) && n > s) out.push(`Batch ${b.name}: ${n} students is more than the whole class (${s}).`);
  });
  if (new Set(d.batches.map((b) => b.name.trim().toLowerCase())).size !== d.batches.length) out.push("Batch names must be different.");
  return out;
}

/** Class sections (programme + semester + section) and their lab batches. */
function ClassesEditor({ programme, readOnly }: { programme: Programme; readOnly: boolean }) {
  const groups = useAll<Group>("groups", { programme_id: programme.id });
  const rooms = useAll<Room>("rooms");
  const save = useSave<Group>("groups");
  const remove = useRemove("groups");
  const [draft, setDraft] = useState<DraftGroup | null>(null);
  const roomCode = (id: string | null) => rooms.data?.find((r) => r.id === id)?.code;
  const issues = draft ? problems(draft) : [];
  const batchSum = draft?.batches.reduce((a, b) => a + (Number(b.strength) || 0), 0) ?? 0;

  const submit = () => {
    if (!draft || issues.length) return;
    const fields = {
      semester: draft.semester, section: draft.section.toUpperCase(), strength: Number(draft.strength),
      home_room_id: draft.home_room_id || null,
      batches: draft.batches.map((b) => ({ name: b.name.trim(), strength: Number(b.strength) })),
    };
    const body = draft.id ? fields : { programme_id: programme.id, ...fields };
    save.mutate({ id: draft.id, body }, {
      onSuccess: () => { toast.success("Class saved"); setDraft(null); },
      onError: (e) => toast.error(e instanceof ApiError ? (e.errors[0]?.message ?? e.message) : "Could not save"),
    });
  };
  const sorted = [...(groups.data ?? [])].sort((a, b) => a.semester - b.semester || a.section.localeCompare(b.section));

  return (
    <div className="mt-8 border-t border-line pt-6">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Layers className="size-4 text-brand" /> Class sections & lab batches
          <HelpTip>A class is one group of students who attend lectures together, e.g. “{programme.code} · Semester 1 · Section A · 40 students”.
            If labs are taken in smaller groups, split it into batches (e.g. B1 = 20, B2 = 20); otherwise labs are for the whole class.</HelpTip></h3>
        {!draft && !readOnly && <Button size="sm" variant="outline" icon={<Plus className="size-4" />}
          onClick={() => setDraft({ semester: 1, section: "A", strength: 40, home_room_id: "", batches: [] })}>Add class</Button>}
      </div>
      <div className="space-y-2">
        {sorted.map((g) => (
          <div key={g.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2.5">
            <div className="flex-1">
              <p className="text-sm font-medium">Semester {g.semester} · Section {g.section}</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                <Badge tone="brand">{g.strength} students</Badge>
                {g.home_room_id && <Badge tone="info">Home classroom: {roomCode(g.home_room_id) ?? "—"}</Badge>}
                {g.batches.length ? g.batches.map((b) => <Badge key={b.id}>{b.name}: {b.strength}</Badge>) : <Badge>Labs: whole class</Badge>}
              </div>
            </div>
            {!readOnly && <>
              <Button size="sm" variant="ghost" onClick={() => setDraft({ id: g.id, semester: g.semester, section: g.section, strength: g.strength, home_room_id: g.home_room_id ?? "", batches: g.batches.map(({ name, strength }) => ({ name, strength })) })}>Edit</Button>
              <IconButton label="Delete class" size="sm" className="hover:text-bad" onClick={() => remove.mutate(g.id)}><Trash2 className="size-4" /></IconButton>
            </>}
          </div>
        ))}
        {groups.data?.length === 0 && !draft && <p className="text-sm text-muted">No classes yet for this programme.</p>}
      </div>
      {draft && (
        <div className="mt-3 space-y-3 rounded-xl border border-brand/30 bg-brand/5 p-4">
          <div className="grid grid-cols-3 gap-3">
            <Field label={`Semester (1–${programme.duration_semesters})`}>
              <Select value={draft.semester} onChange={(e) => setDraft({ ...draft, semester: Number(e.target.value) })}>
                {Array.from({ length: programme.duration_semesters }, (_, i) => <option key={i} value={i + 1}>Semester {i + 1}</option>)}
              </Select>
            </Field>
            <Field label="Section"><Input value={draft.section} maxLength={8} onChange={(e) => setDraft({ ...draft, section: e.target.value })} /></Field>
            <Field label="Number of students">
              <Input type="number" min={1} max={MAX_STRENGTH} step={1} value={draft.strength}
                onChange={(e) => setDraft({ ...draft, strength: e.target.value === "" ? "" : Math.min(Number(e.target.value), 99999) })} />
            </Field>
          </div>
          <Field label="Home classroom (venue)" help="The room printed as “Venue” on the class timetable. Lectures are placed there whenever it is free.">
            <Select value={draft.home_room_id} onChange={(e) => setDraft({ ...draft, home_room_id: e.target.value })}>
              <option value="">No preference</option>
              {rooms.data?.filter((r) => r.is_active).map((r) => <option key={r.id} value={r.id}>{r.code} — {r.name} ({r.capacity} seats)</option>)}
            </Select>
          </Field>
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted">Lab batches {draft.batches.length > 0 && <span className={batchSum === Number(draft.strength) ? "text-ok" : "text-warn"}>· total {batchSum} of {draft.strength || 0}</span>}</p>
            <div className="space-y-2">
              {draft.batches.map((b, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input aria-label="Batch name" value={b.name} maxLength={16} onChange={(e) => setDraft({ ...draft, batches: draft.batches.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
                  <Input aria-label="Students in batch" type="number" min={1} max={MAX_STRENGTH} value={b.strength}
                    onChange={(e) => setDraft({ ...draft, batches: draft.batches.map((x, j) => j === i ? { ...x, strength: e.target.value === "" ? "" : Number(e.target.value) } : x) })} />
                  <IconButton label="Remove batch" size="sm" onClick={() => setDraft({ ...draft, batches: draft.batches.filter((_, j) => j !== i) })}><X className="size-4" /></IconButton>
                </div>
              ))}
              {!draft.batches.length && <p className="text-xs text-muted">No batches: labs are held for the whole class.</p>}
              <Button size="sm" variant="ghost" icon={<Plus className="size-4" />}
                onClick={() => setDraft({ ...draft, batches: [...draft.batches, { name: `B${draft.batches.length + 1}`, strength: "" }] })}>Add batch</Button>
            </div>
          </div>
          {issues.length > 0 && <ul className="space-y-1 rounded-lg bg-bad/8 p-2.5 text-xs text-bad">{issues.map((m) => <li key={m}>• {m}</li>)}</ul>}
          {!issues.length && draft.batches.length > 0 && batchSum !== Number(draft.strength) &&
            <p className="text-xs text-warn">Batch totals ({batchSum}) differ from the class size ({draft.strength}). That's allowed, but check it's intended.</p>}
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button>
            <Button size="sm" loading={save.isPending} disabled={issues.length > 0} onClick={submit}>Save class</Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProgrammesPage() {
  const { hasRole } = useAuth();
  // Only admins can list coordinator accounts; others still see the assigned coordinator's name.
  const coordinators = useQuery({
    queryKey: ["users", "coordinators"],
    queryFn: async () => (await api.get<Paged<UserRow>>("/users?role=COORDINATOR&size=100")).items,
    enabled: hasRole("ADMIN"),
  });
  const cfg: ResourceConfig<Programme> = {
    resource: "programmes", title: "Programmes", singular: "Programme", icon: <GraduationCap />,
    description: "Academic programmes (branches), their class sections and lab batches",
    label: (r) => r.code,
    columns: [
      { key: "code", header: "Code", cell: (r) => <span className="font-medium">{r.code}</span> },
      { key: "name", header: "Name", cell: (r) => r.name },
      { key: "level", header: "Level", cell: (r) => <Badge tone={r.level === "PG" ? "brand" : r.level === "INTEGRATED" ? "info" : "neutral"}>{r.level}</Badge>, hideOnMobile: true },
      { key: "coord", header: "Coordinator", cell: (r) => r.coordinator ? r.coordinator.full_name : <span className="text-muted">Not assigned</span>, hideOnMobile: true },
      { key: "dur", header: "Duration", cell: (r) => `${r.duration_semesters} semesters`, hideOnMobile: true },
    ],
    fields: [
      { name: "code", label: "Code", required: true, half: true, placeholder: "MSC-DFIS" },
      { name: "level", label: "Level", type: "select", options: LEVELS, required: true, half: true },
      { name: "name", label: "Programme name", required: true, placeholder: "M.Sc. Digital Forensics & Information Security" },
      { name: "school", label: "School", type: "select", options: SCHOOLS, required: true },
      { name: "duration_semesters", label: "Total semesters (programme duration)", type: "number", min: 1, max: 12, required: true, half: true,
        help: "The length of the programme, e.g. 4 for a 2-year M.Sc. or 10 for a 5-year integrated programme — not the current semester." },
      { name: "coordinator_id", label: "Programme coordinator", type: "select", half: true, placeholder: "Not assigned",
        options: coordinators.data?.filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.full_name })) ?? [],
        hint: hasRole("ADMIN") ? "Coordinator accounts are created under Users." : "Only admins can change the coordinator." },
    ],
    emptyValues: { code: "", name: "", level: "PG", school: SCHOOLS[0].value, duration_semesters: 4, coordinator_id: "" },
    toValues: (r) => ({ ...r, coordinator_id: r.coordinator_id ?? "" }),
    toBody: (v) => (hasRole("ADMIN") ? v : { ...v, coordinator_id: undefined }),
    filters: (set, f) => (
      <Select aria-label="Filter by level" className="w-40" value={f.level ?? ""} onChange={(e) => set("level", e.target.value)}>
        <option value="">All levels</option>
        {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
      </Select>
    ),
    extraTabs: (row, readOnly) => <ClassesEditor programme={row} readOnly={readOnly} />,
  };
  return <ResourcePage cfg={cfg} />;
}

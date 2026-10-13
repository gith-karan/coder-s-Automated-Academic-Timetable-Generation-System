import { useState } from "react";
import { GraduationCap, Layers, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAll, useRemove, useSave } from "@/lib/hooks";
import type { Group, Paged, Programme, Room, UserRow } from "@/lib/types";
import { useAuth } from "@/app/auth";
import { Button, IconButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { Input, Select } from "@/components/ui/form";
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

interface DraftGroup {
  id?: string; semester: number; section: string; strength: number; home_room_id: string;
  batches: { name: string; strength: number }[];
}

/** Class sections and practical batches of one programme (PS input: programme, semester, section, strength, batches). */
function ClassesEditor({ programme }: { programme: Programme }) {
  const groups = useAll<Group>("groups", { programme_id: programme.id });
  const rooms = useAll<Room>("rooms");
  const roomCode = (id: string | null) => rooms.data?.find((r) => r.id === id)?.code;
  const save = useSave<Group>("groups");
  const remove = useRemove("groups");
  const [draft, setDraft] = useState<DraftGroup | null>(null);

  const submit = () => {
    if (!draft) return;
    const sum = draft.batches.reduce((a, b) => a + b.strength, 0);
    if (draft.batches.length && sum !== draft.strength)
      toast.warning(`Batch strengths add up to ${sum}, but the class has ${draft.strength} students.`);
    const fields = { semester: draft.semester, section: draft.section, strength: draft.strength,
      home_room_id: draft.home_room_id || null, batches: draft.batches };
    const body = draft.id ? fields : { programme_id: programme.id, ...fields };
    save.mutate({ id: draft.id, body }, {
      onSuccess: () => { toast.success("Class saved"); setDraft(null); },
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save"),
    });
  };

  return (
    <div className="mt-8 border-t border-line pt-6">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Layers className="size-4 text-brand" /> Classes & practical batches</h3>
        {!draft && <Button size="sm" variant="outline" icon={<Plus className="size-4" />}
          onClick={() => setDraft({ semester: 1, section: "A", strength: 40, home_room_id: "", batches: [] })}>Add class</Button>}
      </div>
      <div className="space-y-2">
        {groups.data?.map((g) => (
          <div key={g.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2.5">
            <div className="flex-1">
              <p className="text-sm font-medium">Semester {g.semester} · Section {g.section}</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                <Badge tone="brand">{g.strength} students</Badge>
                {g.home_room_id && <Badge tone="info">Venue: {roomCode(g.home_room_id) ?? "—"}</Badge>}
                {g.batches.map((b) => <Badge key={b.id}>{b.name}: {b.strength}</Badge>)}
              </div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setDraft({ id: g.id, semester: g.semester, section: g.section, strength: g.strength, home_room_id: g.home_room_id ?? "", batches: g.batches.map(({ name, strength }) => ({ name, strength })) })}>Edit</Button>
            <IconButton label="Delete class" size="sm" className="hover:text-bad" onClick={() => remove.mutate(g.id)}><Trash2 className="size-4" /></IconButton>
          </div>
        ))}
        {groups.data?.length === 0 && !draft && <p className="text-sm text-muted">No classes yet for this programme.</p>}
      </div>
      {draft && (
        <div className="mt-3 space-y-3 rounded-xl border border-brand/30 bg-brand/5 p-4">
          <div className="grid grid-cols-3 gap-3">
            <label className="text-xs text-muted">Semester
              <Select value={draft.semester} onChange={(e) => setDraft({ ...draft, semester: Number(e.target.value) })}>
                {Array.from({ length: programme.duration_semesters }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
              </Select>
            </label>
            <label className="text-xs text-muted">Section<Input value={draft.section} maxLength={8} onChange={(e) => setDraft({ ...draft, section: e.target.value })} /></label>
            <label className="text-xs text-muted">Strength<Input type="number" min={1} value={draft.strength} onChange={(e) => setDraft({ ...draft, strength: Number(e.target.value) })} /></label>
          </div>
          <label className="block text-xs text-muted">Home classroom (venue) — lectures are placed here when possible
            <Select value={draft.home_room_id} onChange={(e) => setDraft({ ...draft, home_room_id: e.target.value })}>
              <option value="">No preference</option>
              {rooms.data?.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.name} ({r.capacity} seats)</option>)}
            </Select>
          </label>
          {!draft.batches.length && <p className="text-xs text-muted">No practical batches: labs are held for the whole class.</p>}
          <div>
            <p className="mb-1.5 text-xs text-muted">Practical batches</p>
            <div className="space-y-2">
              {draft.batches.map((b, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input aria-label="Batch name" value={b.name} maxLength={16} onChange={(e) => setDraft({ ...draft, batches: draft.batches.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
                  <Input aria-label="Batch strength" type="number" min={1} value={b.strength} onChange={(e) => setDraft({ ...draft, batches: draft.batches.map((x, j) => j === i ? { ...x, strength: Number(e.target.value) } : x) })} />
                  <IconButton label="Remove batch" size="sm" onClick={() => setDraft({ ...draft, batches: draft.batches.filter((_, j) => j !== i) })}><X className="size-4" /></IconButton>
                </div>
              ))}
              <Button size="sm" variant="ghost" icon={<Plus className="size-4" />}
                onClick={() => setDraft({ ...draft, batches: [...draft.batches, { name: `B${draft.batches.length + 1}`, strength: 20 }] })}>Add batch</Button>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button>
            <Button size="sm" loading={save.isPending} onClick={submit}>Save class</Button>
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
    description: "Manage academic programmes, their class sections and practical batches",
    label: (r) => r.code,
    columns: [
      { key: "code", header: "Code", cell: (r) => <span className="font-medium">{r.code}</span> },
      { key: "name", header: "Name", cell: (r) => r.name },
      { key: "level", header: "Level", cell: (r) => <Badge tone={r.level === "PG" ? "brand" : r.level === "INTEGRATED" ? "info" : "neutral"}>{r.level}</Badge>, hideOnMobile: true },
      { key: "coord", header: "Coordinator", cell: (r) => r.coordinator ? r.coordinator.full_name : <span className="text-muted">Not assigned</span>, hideOnMobile: true },
      { key: "sem", header: "Semesters", cell: (r) => r.duration_semesters, className: "text-center", hideOnMobile: true },
    ],
    fields: [
      { name: "code", label: "Code", required: true, half: true, placeholder: "MSC-DFIS" },
      { name: "level", label: "Level", type: "select", options: LEVELS, required: true, half: true },
      { name: "name", label: "Programme name", required: true, placeholder: "M.Sc. Digital Forensics & Information Security" },
      { name: "school", label: "School", type: "select", options: SCHOOLS, required: true },
      { name: "duration_semesters", label: "Number of semesters", type: "number", min: 1, max: 12, required: true, half: true },
      { name: "coordinator_id", label: "Programme coordinator", type: "select", half: true, placeholder: "Not assigned",
        options: coordinators.data?.filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.full_name })) ?? [],
        hint: hasRole("ADMIN") ? "Add coordinators from Users first." : "Only admins can change the coordinator." },
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
    extraTabs: (row) => <ClassesEditor programme={row} />,
  };
  return <ResourcePage cfg={cfg} />;
}

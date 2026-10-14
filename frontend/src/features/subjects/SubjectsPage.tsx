import { BookOpen, FlaskConical, Presentation } from "lucide-react";
import { useAll } from "@/lib/hooks";
import type { Faculty, LabType, Programme, Subject } from "@/lib/types";
import { Badge } from "@/components/ui/display";
import { Select } from "@/components/ui/form";
import { ResourcePage, type ResourceConfig } from "@/components/shared/ResourcePage";

export default function SubjectsPage() {
  const programmes = useAll<Programme>("programmes");
  const faculty = useAll<Faculty>("faculty");
  const labTypes = useAll<LabType>("lab-types");
  const progCode = (id: string) => programmes.data?.find((p) => p.id === id)?.code ?? "—";

  const cfg: ResourceConfig<Subject> = {
    resource: "subjects", title: "Subjects", singular: "Subject", icon: <BookOpen />,
    description: "Manage subjects and practicals with their weekly teaching requirements",
    label: (r) => r.code,
    columns: [
      { key: "code", header: "Code", cell: (r) => <span className="font-medium">{r.code}</span> },
      { key: "short", header: "Short", cell: (r) => <span className="font-semibold text-brand">{r.short_name}</span> },
      { key: "name", header: "Name", cell: (r) => r.name },
      { key: "kind", header: "Type", cell: (r) => r.kind === "THEORY"
          ? <Badge tone="info" icon={<Presentation className="size-3" />}>Theory</Badge>
          : <Badge tone="warn" icon={<FlaskConical className="size-3" />}>Practical</Badge> },
      { key: "prog", header: "Programme", cell: (r) => progCode(r.programme_id), hideOnMobile: true },
      { key: "sem", header: "Sem", cell: (r) => r.semester, className: "text-center", hideOnMobile: true },
      { key: "load", header: "Weekly", cell: (r) => r.kind === "THEORY" ? `${r.periods_per_week} periods` : `${r.sessions_per_week} × ${r.consecutive_periods}p`, hideOnMobile: true },
      { key: "fac", header: "Faculty", cell: (r) => <span className="text-muted">{r.faculty.map((f) => f.name).join(", ") || "—"}</span>, hideOnMobile: true },
    ],
    fields: [
      { name: "programme_id", label: "Programme", type: "select", required: true, half: true,
        options: programmes.data?.map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })) ?? [] },
      { name: "semester", label: "Semester", type: "select", required: true, half: true,
        options: (v) => Array.from({ length: programmes.data?.find((p) => p.id === v.programme_id)?.duration_semesters ?? 0 },
          (_, i) => ({ value: String(i + 1), label: `Semester ${i + 1}` })),
        placeholder: "Choose the programme first" },
      { name: "code", label: "Code", required: true, half: true, placeholder: "MSDF26-PC-101" },
      { name: "kind", label: "Type", type: "select", required: true, half: true,
        options: [{ value: "THEORY", label: "Theory" }, { value: "PRACTICAL", label: "Practical / lab" }] },
      { name: "name", label: "Subject name", required: true, half: true, placeholder: "Vulnerability Assessment and Penetration Testing" },
      { name: "short_name", label: "Short name", required: true, half: true, placeholder: "VAPT",
        help: "The abbreviation shown on timetables, e.g. VAPT, RM, EM-1 (up to 16 characters).",
        validate: (v) => (typeof v === "string" && v.length > 16 ? "At most 16 characters" : undefined) },
      { name: "periods_per_week", label: "Theory periods per week", type: "number", min: 1, max: 20, required: true, half: true, show: (v) => v.kind === "THEORY" },
      { name: "sessions_per_week", label: "Practical sessions per week", type: "number", min: 1, max: 10, required: true, half: true, show: (v) => v.kind === "PRACTICAL",
        hint: "Per batch" },
      { name: "consecutive_periods", label: "Consecutive periods per session", type: "number", min: 1, max: 6, required: true, half: true, show: (v) => v.kind === "PRACTICAL" },
      { name: "lab_type_id", label: "Required laboratory type", type: "select", required: true, show: (v) => v.kind === "PRACTICAL",
        options: labTypes.data?.map((l) => ({ value: l.id, label: l.name })) ?? [] },
      { name: "credits", label: "Credits", type: "number", min: 0, max: 20, half: true },
      { name: "faculty_ids", label: "Assigned faculty", type: "multiselect", required: true,
        emptyText: "Choose the programme first",
        help: "Only faculty allowed to teach in this programme are listed (set under Faculty → Can teach in).",
        options: (v) => !v.programme_id ? [] : (faculty.data ?? [])
          .filter((f) => !f.programme_ids.length || f.programme_ids.includes(String(v.programme_id))
            || ((v.faculty_ids as string[]) ?? []).includes(f.id))
          .map((f) => ({ value: f.id, label: `${f.name} (${f.code})` })) },
    ],
    emptyValues: { code: "", name: "", short_name: "", kind: "THEORY", programme_id: "", semester: "1", periods_per_week: 3, sessions_per_week: 1, consecutive_periods: 2, lab_type_id: "", credits: 4, faculty_ids: [] },
    toValues: (r) => ({ ...r, semester: String(r.semester), faculty_ids: r.faculty.map((f) => f.id), lab_type_id: r.lab_type_id ?? "" }),
    toBody: (v) => {
      const b = { ...v, semester: Number(v.semester) } as Record<string, unknown>;
      if (b.kind === "THEORY") { b.sessions_per_week = 0; b.consecutive_periods = 1; b.lab_type_id = null; }
      else b.periods_per_week = 0;
      return b;
    },
    filters: (set, f) => (
      <>
        <Select aria-label="Filter by programme" className="w-48" value={f.programme_id ?? ""} onChange={(e) => set("programme_id", e.target.value)}>
          <option value="">All programmes</option>
          {programmes.data?.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
        </Select>
        <Select aria-label="Filter by type" className="w-36" value={f.kind ?? ""} onChange={(e) => set("kind", e.target.value)}>
          <option value="">All types</option><option value="THEORY">Theory</option><option value="PRACTICAL">Practical</option>
        </Select>
      </>
    ),
  };
  return <ResourcePage cfg={cfg} />;
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CalendarDays, Users } from "lucide-react";
import { api } from "@/lib/api";
import { useAll } from "@/lib/hooks";
import type { ConstraintItem, Faculty, Programme } from "@/lib/types";
import { initials } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { HelpTip } from "@/components/ui/overlay";
import { Badge } from "@/components/ui/display";
import { Select } from "@/components/ui/form";
import { ResourcePage, type ResourceConfig } from "@/components/shared/ResourcePage";
import { SCHOOLS } from "@/features/programmes/ProgrammesPage";
import { AvailabilityEditor } from "./AvailabilityEditor";

const DESIGNATIONS = ["Faculty", "Professor", "Associate Professor", "Assistant Professor", "Visiting Faculty", "Adjunct Professor", "Lab Instructor"]
  .map((d) => ({ value: d, label: d }));

export default function FacultyPage() {
  const { can } = useAuth();
  const programmes = useAll<Programme>("programmes");
  const constraints = useQuery({
    queryKey: ["constraints"],
    queryFn: () => api.get<{ configurable: ConstraintItem[] }>("/constraints"),
    enabled: can("setup.view"),
  });
  const daily = constraints.data?.configurable.find((c) => c.key === "faculty_max_per_day");
  const defaultText = daily ? (daily.mode === "OFF" ? "no limit" : `${daily.value} per day`) : "…";
  const progCode = (id: string) => programmes.data?.find((p) => p.id === id)?.code ?? "?";

  const cfg: ResourceConfig<Faculty> = {
    resource: "faculty", title: "Faculty", singular: "Faculty member", icon: <Users />,
    description: "Faculty details, the programmes they may teach in, teaching limits and weekly availability",
    label: (r) => r.name, drawerWidth: "max-w-2xl",
    columns: [
      { key: "code", header: "Code", cell: (r) => <span className="font-medium">{r.code}</span> },
      { key: "name", header: "Name", cell: (r) => (
        <span className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-full bg-brand/10 text-[11px] font-bold text-brand">{initials(r.name)}</span>{r.name}
        </span>) },
      { key: "prog", header: "Can teach in", hideOnMobile: true, cell: (r) => r.programme_ids.length
          ? <span className="flex flex-wrap gap-1">{r.programme_ids.map((id) => <Badge key={id}>{progCode(id)}</Badge>)}</span>
          : <span className="text-xs text-muted">Any programme</span> },
      { key: "email", header: "Email", cell: (r) => <span className="text-muted">{r.email}</span>, hideOnMobile: true },
      { key: "lim", header: "Max / day", cell: (r) => r.max_periods_per_day ?? <span className="text-muted">Default</span>, className: "text-center", hideOnMobile: true },
    ],
    fields: [
      { name: "code", label: "Faculty code (initials)", required: true, half: true, placeholder: "KP" },
      { name: "designation", label: "Designation", type: "select", options: DESIGNATIONS, required: true, half: true },
      { name: "name", label: "Full name", required: true, placeholder: "Ms. Krupali Panchal" },
      { name: "email", label: "Email", type: "email", required: true, placeholder: "name@nfsu.ac.in",
        validate: (v) => (typeof v === "string" && v && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? "Enter a valid email" : undefined) },
      { name: "school", label: "School", type: "select", options: SCHOOLS, required: true },
      { name: "programme_ids", label: "Can teach in programmes", type: "multiselect",
        emptyText: "No programmes in this school yet",
        help: "Only these programmes' subjects can be assigned to this faculty member. Leave all unselected to allow any programme.",
        options: (v) => (programmes.data ?? [])
          .filter((p) => p.school === v.school || ((v.programme_ids as string[]) ?? []).includes(p.id))
          .map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })) },
      { name: "max_periods_per_day", label: "Max periods per day", type: "number", min: 1, max: 16, half: true,
        hint: <>Leave blank to use the university default (<b>{defaultText}</b>), set in <Link to="/constraints" className="text-brand underline">Constraints</Link>.</> },
      { name: "max_periods_per_week", label: "Max periods per week", type: "number", min: 1, max: 80, half: true, hint: "Leave blank for no weekly limit." },
    ],
    emptyValues: { code: "", name: "", email: "", designation: "Faculty", school: SCHOOLS[0].value, programme_ids: [], max_periods_per_day: "", max_periods_per_week: "" },
    toValues: (r) => ({ ...r, max_periods_per_day: r.max_periods_per_day ?? "", max_periods_per_week: r.max_periods_per_week ?? "" }),
    toBody: (v) => { const b = { ...v }; delete b.availability; return b; },
    filters: (set, f) => (
      <Select aria-label="Filter by school" className="w-64" value={f.school ?? ""} onChange={(e) => set("school", e.target.value)}>
        <option value="">All schools</option>
        {SCHOOLS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
      </Select>
    ),
    extraTabs: (row, readOnly) => (
      <div className="mt-8 border-t border-line pt-6">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><CalendarDays className="size-4 text-brand" /> Weekly availability
          <HelpTip>The generator schedules this person only in green or gold periods (gold = preferred). Blue periods are fixed commitments.</HelpTip></h3>
        <AvailabilityEditor faculty={row} canEdit={!readOnly} />
      </div>
    ),
  };
  return <ResourcePage cfg={cfg} />;
}

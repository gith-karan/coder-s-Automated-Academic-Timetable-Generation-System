import { CalendarDays, Users } from "lucide-react";
import type { Faculty } from "@/lib/types";
import { initials } from "@/lib/utils";
import { Select } from "@/components/ui/form";
import { ResourcePage, type ResourceConfig } from "@/components/shared/ResourcePage";
import { SCHOOLS } from "@/features/programmes/ProgrammesPage";
import { AvailabilityEditor } from "./AvailabilityEditor";

const DESIGNATIONS = ["Faculty", "Professor", "Associate Professor", "Assistant Professor", "Visiting Faculty", "Adjunct Professor", "Lab Instructor"]
  .map((d) => ({ value: d, label: d }));

export default function FacultyPage() {
  const cfg: ResourceConfig<Faculty> = {
    resource: "faculty", title: "Faculty", singular: "Faculty member", icon: <Users />,
    description: "Manage faculty details, teaching limits and weekly availability",
    label: (r) => r.name, drawerWidth: "max-w-2xl",
    columns: [
      { key: "code", header: "Code", cell: (r) => <span className="font-medium">{r.code}</span> },
      { key: "name", header: "Name", cell: (r) => (
        <span className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-full bg-brand/10 text-[11px] font-bold text-brand">{initials(r.name)}</span>{r.name}
        </span>) },
      { key: "des", header: "Designation", cell: (r) => r.designation, hideOnMobile: true },
      { key: "email", header: "Email", cell: (r) => <span className="text-muted">{r.email}</span>, hideOnMobile: true },
      { key: "lim", header: "Max / day", cell: (r) => r.max_periods_per_day ?? "Default", className: "text-center", hideOnMobile: true },
    ],
    fields: [
      { name: "code", label: "Faculty code", required: true, half: true, placeholder: "F001" },
      { name: "designation", label: "Designation", type: "select", options: DESIGNATIONS, required: true, half: true },
      { name: "name", label: "Full name", required: true, placeholder: "Dr. R. Sharma" },
      { name: "email", label: "Email", type: "email", required: true, placeholder: "name@nfsu.ac.in",
        validate: (v) => (typeof v === "string" && v && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? "Enter a valid email" : undefined) },
      { name: "school", label: "School", type: "select", options: SCHOOLS, required: true },
      { name: "max_periods_per_day", label: "Max periods per day", type: "number", min: 1, max: 16, half: true, hint: "Blank = university default" },
      { name: "max_periods_per_week", label: "Max periods per week", type: "number", min: 1, max: 80, half: true },
    ],
    emptyValues: { code: "", name: "", email: "", designation: "Assistant Professor", school: SCHOOLS[0].value, max_periods_per_day: "", max_periods_per_week: "" },
    toValues: (r) => ({ ...r, max_periods_per_day: r.max_periods_per_day ?? "", max_periods_per_week: r.max_periods_per_week ?? "" }),
    toBody: (v) => { const b = { ...v }; delete b.availability; return b; },
    filters: (set, f) => (
      <Select aria-label="Filter by school" className="w-64" value={f.school ?? ""} onChange={(e) => set("school", e.target.value)}>
        <option value="">All schools</option>
        {SCHOOLS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
      </Select>
    ),
    extraTabs: (row) => (
      <div className="mt-8 border-t border-line pt-6">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold"><CalendarDays className="size-4 text-brand" /> Weekly availability</h3>
        <p className="mb-4 text-xs text-muted">The generator schedules {row.name} only in green or gold periods. Gold marks preferred teaching time.</p>
        <AvailabilityEditor faculty={row} />
      </div>
    ),
  };
  return <ResourcePage cfg={cfg} />;
}

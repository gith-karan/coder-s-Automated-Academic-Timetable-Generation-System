import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, FlaskConical, School } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAll, useSave } from "@/lib/hooks";
import type { CalendarData, LabType, Room } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { Select } from "@/components/ui/form";
import { ResourcePage, type ResourceConfig } from "@/components/shared/ResourcePage";
import { availabilityToSlots, SlotPainter, slotsToAvailability } from "@/components/shared/SlotPainter";

function RoomBlocks({ room }: { room: Room }) {
  const cal = useQuery({ queryKey: ["calendar"], queryFn: () => api.get<CalendarData>("/calendar") });
  const save = useSave<Room>("rooms");
  const initial = useMemo(() => (cal.data ? availabilityToSlots(cal.data.grid, { unavailable: room.unavailable }) : null), [cal.data, room]);
  const [slots, setSlots] = useState(initial);
  useEffect(() => setSlots(initial), [initial]);
  if (!cal.data || !slots) return null;
  return (
    <div className="mt-8 border-t border-line pt-6">
      <h3 className="mb-1 text-sm font-semibold">Availability</h3>
      <p className="mb-4 text-xs text-muted">Block periods when this room cannot be used (maintenance, exams, other departments).</p>
      <SlotPainter grid={cal.data.grid} value={slots} onChange={setSlots} brushes={["available", "unavailable"]} />
      <div className="mt-3 flex justify-end">
        <Button size="sm" loading={save.isPending}
          onClick={() => save.mutate({ id: room.id, body: { unavailable: slotsToAvailability(cal.data.grid, slots, {}).unavailable } },
            { onSuccess: () => toast.success("Room availability saved") })}>Save availability</Button>
      </div>
    </div>
  );
}

export default function RoomsPage() {
  const labTypes = useAll<LabType>("lab-types");
  const cfg: ResourceConfig<Room> = {
    resource: "rooms", title: "Classrooms & Laboratories", singular: "Room", icon: <Building2 />,
    description: "Manage rooms and lab facilities, their capacity and availability",
    label: (r) => r.code, drawerWidth: "max-w-2xl",
    columns: [
      { key: "code", header: "Code", cell: (r) => <span className="font-medium">{r.code}</span> },
      { key: "name", header: "Name", cell: (r) => r.name },
      { key: "kind", header: "Type", cell: (r) => r.kind === "LAB"
          ? <Badge tone="warn" icon={<FlaskConical className="size-3" />}>{r.lab_type?.name ?? "Lab"}</Badge>
          : <Badge tone="info" icon={<School className="size-3" />}>Classroom</Badge> },
      { key: "cap", header: "Capacity", cell: (r) => <span className="tabular-nums">{r.capacity}</span>, className: "text-center" },
      { key: "bld", header: "Building", cell: (r) => <span className="text-muted">{r.building ?? "—"}</span>, hideOnMobile: true },
      { key: "act", header: "Status", cell: (r) => r.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>, hideOnMobile: true },
    ],
    fields: [
      { name: "code", label: "Room number / code", required: true, half: true, placeholder: "SCSDF-101" },
      { name: "kind", label: "Type", type: "select", required: true, half: true, options: [{ value: "CLASSROOM", label: "Classroom" }, { value: "LAB", label: "Laboratory" }] },
      { name: "name", label: "Name", required: true, placeholder: "Classroom 101" },
      { name: "lab_type_id", label: "Laboratory type", type: "select", required: true, show: (v) => v.kind === "LAB",
        options: labTypes.data?.map((l) => ({ value: l.id, label: l.name })) ?? [] },
      { name: "capacity", label: "Seating capacity", type: "number", min: 1, max: 2000, required: true, half: true },
      { name: "building", label: "Building", half: true, placeholder: "SCSDF Block" },
      { name: "is_active", label: "Available for scheduling", type: "switch" },
    ],
    emptyValues: { code: "", name: "", kind: "CLASSROOM", lab_type_id: "", capacity: 60, building: "", is_active: true },
    toValues: (r) => ({ ...r, lab_type_id: r.lab_type_id ?? "", building: r.building ?? "" }),
    toBody: (v) => { const b = { ...v }; if (b.kind === "CLASSROOM") b.lab_type_id = null; return b; },
    filters: (set, f) => (
      <Select aria-label="Filter by type" className="w-40" value={f.kind ?? ""} onChange={(e) => set("kind", e.target.value)}>
        <option value="">All rooms</option><option value="CLASSROOM">Classrooms</option><option value="LAB">Laboratories</option>
      </Select>
    ),
    extraTabs: (row) => <RoomBlocks room={row} />,
  };
  return <ResourcePage cfg={cfg} />;
}

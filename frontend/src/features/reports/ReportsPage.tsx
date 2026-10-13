import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Building2, Download, Users } from "lucide-react";
import { api, downloadUrl } from "@/lib/api";
import type { TimetableSummary, TimetableView } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, PageHeader, Progress, Skeleton } from "@/components/ui/display";
import { Field, Select } from "@/components/ui/form";
import { StatCard } from "@/components/shared/widgets";

export default function ReportsPage() {
  const list = useQuery({ queryKey: ["timetables"], queryFn: () => api.get<TimetableSummary[]>("/timetables") });
  const [picked, setPicked] = useState<string>("");
  const ttId = picked || list.data?.[0]?.id;
  const { data } = useQuery({ queryKey: ["timetable", ttId, "all"], queryFn: () => api.get<TimetableView>(`/timetables/${ttId}`), enabled: !!ttId });

  const stats = useMemo(() => {
    if (!data) return null;
    const perWeek = data.grid.periods_per_week;
    const fac = new Map<string, { name: string; n: number }>();
    const room = new Map<string, { name: string; n: number }>();
    for (const e of data.entries) {
      e.faculty.forEach((f) => fac.set(f.id, { name: f.name, n: (fac.get(f.id)?.n ?? 0) + e.length }));
      if (e.room) room.set(e.room.id, { name: `${e.room.code} · ${e.room.name}`, n: (room.get(e.room.id)?.n ?? 0) + e.length });
    }
    const sort = (m: Map<string, { name: string; n: number }>) => [...m.values()].sort((a, b) => b.n - a.n);
    const roomList = sort(room);
    const avgRoom = roomList.length ? roomList.reduce((a, r) => a + r.n, 0) / roomList.length / perWeek : 0;
    return { perWeek, faculty: sort(fac), rooms: roomList, avgRoom };
  }, [data]);

  return (
    <>
      <PageHeader title="Reports" description="Faculty workload and room utilisation for a timetable"
        actions={ttId && <Button variant="outline" icon={<Download className="size-4" />} onClick={() => downloadUrl(`/timetables/${ttId}/export?format=xlsx`)}>Download Excel</Button>} />
      <div className="mb-5 w-80">
        <Field label="Timetable">
          <Select value={ttId ?? ""} onChange={(e) => setPicked(e.target.value)}>
            {list.data?.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.status.toLowerCase()}</option>)}
          </Select>
        </Field>
      </div>
      {!list.data?.length ? <Card><EmptyState icon={<BarChart3 />} title="No timetables yet" /></Card> : !stats ? <Skeleton className="h-96" /> : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Sessions placed" value={data!.entries.length} icon={<BarChart3 />} />
            <StatCard label="Faculty teaching" value={stats.faculty.length} icon={<Users />} tone="gold" />
            <StatCard label="Rooms in use" value={stats.rooms.length} icon={<Building2 />} tone="info" />
            <StatCard label="Avg. room utilisation" value={`${Math.round(stats.avgRoom * 100)}%`} icon={<Building2 />} tone="ok" />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Faculty workload" description="Teaching periods per week">
              <ul className="space-y-3">
                {stats.faculty.map((f) => (
                  <li key={f.name}>
                    <div className="mb-1 flex justify-between text-sm"><span>{f.name}</span><span className="tabular-nums text-muted">{f.n} periods</span></div>
                    <Progress value={(f.n / Math.max(...stats.faculty.map((x) => x.n))) * 100} tone={f.n > 18 ? "warn" : "brand"} />
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Room utilisation" description={`Share of the ${stats.perWeek} weekly periods in use`}>
              <ul className="space-y-3">
                {stats.rooms.map((r) => (
                  <li key={r.name}>
                    <div className="mb-1 flex justify-between text-sm"><span>{r.name}</span><span className="tabular-nums text-muted">{Math.round((r.n / stats.perWeek) * 100)}%</span></div>
                    <Progress value={(r.n / stats.perWeek) * 100} tone={r.n / stats.perWeek > 0.85 ? "warn" : "ok"} />
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}
    </>
  );
}

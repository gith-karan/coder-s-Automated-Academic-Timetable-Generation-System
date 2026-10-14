import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, CalendarRange, CheckCircle2, ClipboardList, Download, Layers, RefreshCw, Timer, XCircle } from "lucide-react";
import { api, downloadUrl } from "@/lib/api";
import type { Run } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTimeFormat } from "@/app/preferences";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, PageHeader, Progress, Skeleton, Tabs } from "@/components/ui/display";
import { DataTable } from "@/components/ui/table";
import { DiagnosticList, RunStatusBadge, StatCard } from "@/components/shared/widgets";

export default function ReportPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState("summary");
  const { tx, dt } = useTimeFormat();
  const { data: run } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.get<Run>(`/runs/${runId}`),
    refetchInterval: (q) => (q.state.data && ["QUEUED", "RUNNING"].includes(q.state.data.status) ? 1500 : false),
  });
  if (!run) return <Skeleton className="h-96" />;

  const ok = run.status === "SUCCESS";
  const s = run.stats;
  const errors = run.diagnostics.filter((d) => d.severity === "ERROR");
  const q = s.quality;
  const banner = ok
    ? { cls: "bg-ok/10 text-ok border-ok/30", icon: <CheckCircle2 className="size-5" />, text: "Timetable generated successfully! Every mandatory rule is satisfied." }
    : run.status === "PRECHECK_FAILED"
      ? { cls: "bg-bad/10 text-bad border-bad/30", icon: <AlertOctagon className="size-5" />, text: "The inputs make a complete timetable impossible. Nothing was published — fix the problems below and generate again." }
      : run.status === "INFEASIBLE"
        ? { cls: "bg-bad/10 text-bad border-bad/30", icon: <XCircle className="size-5" />, text: "No timetable can satisfy every mandatory rule. A best partial draft was saved (it cannot be published)." }
        : { cls: "bg-warn/10 text-warn border-warn/30", icon: <Timer className="size-5" />, text: run.diagnostics.at(-1)?.message ?? `Generation ${run.status.toLowerCase()}.` };

  return (
    <>
      <PageHeader title="Generation Report" description={`Results and diagnostics · ${dt(run.finished_at ?? run.created_at)}`}
        actions={<>
          <RunStatusBadge status={run.status} />
          <Button variant="secondary" icon={<RefreshCw className="size-4" />} onClick={() => navigate("/generate")}>Regenerate</Button>
          {(ok || run.status === "INFEASIBLE") && <Button icon={<CalendarRange className="size-4" />} onClick={() => navigate(`/timetable?tt=${run.timetable_id}`)}>View timetable</Button>}
        </>} />

      <div role="status" className={cn("mb-5 flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm font-medium", banner.cls)}>{banner.icon}{banner.text}</div>

      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total sessions" value={s.total ?? "—"} icon={<Layers />} />
        <StatCard label="Scheduled" value={s.scheduled ?? 0} icon={<CheckCircle2 />} tone="ok" />
        <StatCard label="Unassigned" value={run.unassigned.length} icon={<ClipboardList />} tone={run.unassigned.length ? "warn" : "ok"} />
        <StatCard label="Conflicts" value={ok ? 0 : errors.length} icon={<AlertOctagon />} tone={ok ? "ok" : "warn"} hint={ok ? "Verified by independent validator" : "Problems to resolve"} />
      </div>

      <Card>
        <Tabs value={tab} onValueChange={setTab} tabs={[
          { value: "summary", label: "Summary" },
          { value: "diagnostics", label: <>Diagnostics {run.diagnostics.length > 0 && <Badge tone={errors.length ? "bad" : "warn"}>{run.diagnostics.length}</Badge>}</> },
          { value: "unassigned", label: <>Unassigned sessions {run.unassigned.length > 0 && <Badge tone="warn">{run.unassigned.length}</Badge>}</> },
        ]} />
        <div className="pt-4">
          {tab === "summary" && (
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <p className="mb-3 text-sm font-semibold">Key metrics</p>
                <dl className="space-y-3 text-sm">
                  {[
                    ["Constraint satisfaction", ok ? "100%" : `${s.total ? Math.round(((s.scheduled ?? 0) / s.total) * 100) : 0}% placed`],
                    ["Quality score", q ? `${q.quality} / 100` : "—"],
                    ["Optimality", s.optimal ? "Proven optimal" : ok ? "Best found within time limit" : "—"],
                    ["Solve time", s.wall_time_s != null ? `${s.wall_time_s}s` : "—"],
                    ["Locked sessions respected", String(s.locked ?? 0)],
                    ["Decision variables", s.variables?.toLocaleString() ?? "—"],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-line/60 pb-2"><dt className="text-muted">{k}</dt><dd className="font-medium tabular-nums">{v}</dd></div>
                  ))}
                </dl>
              </div>
              <div>
                <p className="mb-3 text-sm font-semibold">Preferences honoured</p>
                {q ? (
                  <div className="space-y-4">
                    {Object.entries(q.breakdown).map(([k, b]) => (
                      <div key={k}>
                        <div className="mb-1 flex justify-between text-sm"><span>{b.label}</span><span className="font-medium tabular-nums">{b.score}%</span></div>
                        <Progress value={b.score} tone={b.score >= 85 ? "ok" : b.score >= 60 ? "warn" : "bad"} />
                      </div>
                    ))}
                    <div className="flex gap-2 pt-2">
                      <Button size="sm" variant="outline" icon={<Download className="size-4" />} onClick={() => downloadUrl(`/timetables/${run.timetable_id}/export?format=pdf`)}>PDF</Button>
                      <Button size="sm" variant="outline" icon={<Download className="size-4" />} onClick={() => downloadUrl(`/timetables/${run.timetable_id}/export?format=xlsx`)}>Excel</Button>
                    </div>
                  </div>
                ) : <p className="text-sm text-muted">Not available for this run.</p>}
              </div>
            </div>
          )}
          {tab === "diagnostics" && (
            <DiagnosticList items={run.diagnostics} empty={<EmptyState icon={<CheckCircle2 />} title="No problems found" description="Every mandatory rule is satisfied." />} />
          )}
          {tab === "unassigned" && (
            <DataTable rowKey={(r) => r.key} rows={run.unassigned}
              empty={<EmptyState icon={<CheckCircle2 />} title="Every session was scheduled" />}
              columns={[
                { key: "s", header: "Session", cell: (r) => <span className="font-medium">{r.subject_code ?? "—"}</span> },
                { key: "a", header: "Class / batch", cell: (r) => r.audience ?? "—" },
                { key: "f", header: "Faculty", cell: (r) => r.faculty?.join(", ") ?? "—", hideOnMobile: true },
                { key: "l", header: "Length", cell: (r) => r.length ? `${r.length}p` : "—", hideOnMobile: true },
                { key: "r", header: "Why it could not be placed", cell: (r) => <span className="text-xs text-muted">{r.reason ? tx(r.reason) : "Blocked by input problems listed under Diagnostics"}</span> },
              ]} />
          )}
        </div>
      </Card>
    </>
  );
}

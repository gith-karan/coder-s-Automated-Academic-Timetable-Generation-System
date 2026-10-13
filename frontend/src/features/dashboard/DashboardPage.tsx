import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, BookOpen, Building2, CalendarRange, CheckCircle2, ClipboardCheck, Database, GraduationCap, Plus, Sparkles, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { cn, ROLE_LABEL, timeAgo } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/display";
import { Donut, RunStatusBadge, StatCard, TimetableStatusBadge } from "@/components/shared/widgets";

const ACTIVITY_ICON: Record<string, typeof Activity> = { TIMETABLE: CalendarRange, USER: Users, DATA: Database, WORKFLOW: ClipboardCheck };

export default function DashboardPage() {
  const { me, hasRole } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const staff = hasRole("ADMIN", "COORDINATOR");
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/dashboard") });
  const seed = useMutation({
    mutationFn: () => api.post("/demo/seed"),
    onSuccess: () => { toast.success("NFSU demo data loaded"); void qc.invalidateQueries(); },
  });

  const today = new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  const firstName = me?.full_name.replace(/^(Dr|Prof)\.?\s+/i, "").split(" ")[0];
  const empty = data && data.counts.programmes === 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Welcome back, ${firstName}! Here's what's happening with your timetable.`}
        actions={<>
          <span className="hidden text-sm text-muted sm:inline">{today}</span>
          {staff && <Button icon={<Plus className="size-4" />} onClick={() => navigate("/generate")}>New Timetable</Button>}
        </>}
      />

      {empty && staff && (
        <Card className="mb-5 border-dashed">
          <EmptyState icon={<Sparkles />} title="Let's set up your first timetable"
            description="Add programmes, faculty, rooms and subjects — or load a realistic NFSU dataset (Gandhinagar campus) to explore every feature."
            action={hasRole("ADMIN") && <Button loading={seed.isPending} onClick={() => seed.mutate()} icon={<Database className="size-4" />}>Load NFSU demo data</Button>} />
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {isLoading || !data ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[84px] rounded-2xl" />) : <>
          <StatCard label="Programmes" value={data.counts.programmes} icon={<GraduationCap />} to={staff ? "/programmes" : undefined} hint={`${data.counts.classes} class sections`} />
          <StatCard label="Subjects" value={data.counts.subjects} icon={<BookOpen />} tone="info" to={staff ? "/subjects" : undefined} />
          <StatCard label="Faculty" value={data.counts.faculty} icon={<Users />} tone="gold" to={staff ? "/faculty" : undefined} />
          <StatCard label="Classrooms / Labs" value={data.counts.rooms} icon={<Building2 />} tone="ok" to={staff ? "/rooms" : undefined} hint={`${data.counts.labs} laboratories`} />
        </>}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-5">
        {staff ? (
          <Card className="lg:col-span-3" title="Recent activity" action={hasRole("ADMIN") && <Link to="/audit" className="text-xs font-medium text-brand hover:underline">View audit log</Link>}>
            {!data?.recent_activity?.length ? (
              <p className="py-8 text-center text-sm text-muted">No activity yet.</p>
            ) : (
              <ul className="space-y-1">
                {data.recent_activity.map((a, i) => {
                  const Icon = ACTIVITY_ICON[a.category] ?? Activity;
                  return (
                    <li key={i} className="flex items-start gap-3 rounded-xl px-2 py-2.5 hover:bg-surface-2">
                      <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-ok/12 text-ok"><Icon className="size-4" /></div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{a.summary}</p>
                        <p className="text-xs text-muted">{a.actor ?? "System"}</p>
                      </div>
                      <span className="shrink-0 text-xs text-muted">{timeAgo(a.at)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        ) : (
          <Card className="lg:col-span-3" title="Your timetable">
            {data?.published ? (
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-semibold">{data.published.name}</p>
                  <p className="text-sm text-muted">Published {timeAgo(data.published.published_at)}</p>
                </div>
                <Button icon={<CalendarRange className="size-4" />} onClick={() => navigate("/timetable")}>Open my timetable</Button>
              </div>
            ) : <p className="py-6 text-sm text-muted">No timetable has been published yet. You'll be notified when it is.</p>}
          </Card>
        )}

        <Card className="lg:col-span-2" title="Timetable overview" action={data?.timetable && <TimetableStatusBadge status={data.timetable.status} />}>
          {data?.overview && data.timetable ? (
            <>
              <p className="-mt-1 mb-4 truncate text-xs text-muted">{data.timetable.name}</p>
              <Donut center={`${Math.round(data.timetable.total_sessions ? (100 * data.timetable.scheduled) / data.timetable.total_sessions : 0)}%`} sub="Scheduled"
                segments={[
                  { label: "Room use", value: data.overview.allocated_pct, color: "var(--brand)" },
                  { label: "Free capacity", value: data.overview.available_pct, color: "var(--ok)" },
                ]} />
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                {[["Sessions", data.timetable.total_sessions], ["Unassigned", data.timetable.unassigned], ["Quality", data.overview.quality ?? "—"]].map(([l, v]) => (
                  <div key={l} className="rounded-xl bg-surface-2 py-2">
                    <p className="text-lg font-semibold tabular-nums">{v}</p>
                    <p className="text-[11px] text-muted">{l}</p>
                  </div>
                ))}
              </div>
            </>
          ) : <p className="py-10 text-center text-sm text-muted">No timetable generated yet.</p>}
        </Card>
      </div>

      {staff && data && (
        <div className="mt-5 grid gap-5 md:grid-cols-3">
          <Card title="Last generation">
            {data.last_run ? (
              <div className="flex items-center justify-between">
                <div><RunStatusBadge status={data.last_run.status} /><p className="mt-1 text-xs text-muted">{timeAgo(data.last_run.created_at)}</p></div>
                <Button size="sm" variant="secondary" onClick={() => navigate(`/generate/report/${data.last_run!.id}`)}>View report</Button>
              </div>
            ) : <p className="text-sm text-muted">Not run yet.</p>}
          </Card>
          <Card title="Pending approvals">
            <div className="flex items-center justify-between">
              <p className={cn("text-3xl font-semibold tabular-nums", data.pending_requests ? "text-warn" : "text-ok")}>{data.pending_requests ?? 0}</p>
              <Button size="sm" variant="secondary" onClick={() => navigate("/requests")}>Review</Button>
            </div>
          </Card>
          <Card title="Active users">
            <div className="flex flex-wrap gap-2">
              {data.users && Object.entries(data.users).map(([r, n]) => (
                <span key={r} className="rounded-lg bg-surface-2 px-2.5 py-1 text-xs"><b className="tabular-nums">{n}</b> {ROLE_LABEL[r as keyof typeof ROLE_LABEL]}</span>
              ))}
            </div>
          </Card>
        </div>
      )}
      {data?.published && staff && (
        <p className="mt-5 flex items-center gap-1.5 text-xs text-muted"><CheckCircle2 className="size-3.5 text-ok" /> Live timetable: <b>{data.published.name}</b> · published {timeAgo(data.published.published_at)}</p>
      )}
    </>
  );
}

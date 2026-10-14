import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, BookOpen, Building2, CalendarRange, ClipboardCheck, Database, GraduationCap, Info, Plus, Sparkles, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Dashboard, TimetableSummary } from "@/lib/types";
import { cn, ROLE_LABEL, timeAgo } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/display";
import { Select } from "@/components/ui/form";
import { Tip } from "@/components/ui/overlay";
import { Donut, RunStatusBadge, StatCard, TimetableStatusBadge } from "@/components/shared/widgets";

const ACTIVITY_ICON: Record<string, typeof Activity> = { TIMETABLE: CalendarRange, USER: Users, DATA: Database, WORKFLOW: ClipboardCheck };
const TERM = { ODD: "Odd term (Sem I, III, V…)", EVEN: "Even term (Sem II, IV, VI…)" } as const;

const STATUS_TEXT = { DRAFT: "Draft", IN_REVIEW: "Awaiting approval", PUBLISHED: "Published" } as const;

/** Donut overview of ONE timetable, chosen from a dropdown (published first, then drafts). */
function TimetableOverview({ list }: { list: TimetableSummary[] }) {
  const navigate = useNavigate();
  const [picked, setPicked] = useState<string>("");
  const t = list.find((x) => x.id === picked) ?? list[0];
  if (!t) return <p className="flex items-center gap-2 py-10 text-sm text-muted"><Info className="size-4" />No timetable yet.</p>;
  const scheduledPct = t.total_sessions ? Math.round((100 * t.scheduled) / t.total_sessions) : 0;
  return (
    <div className="space-y-4">
      <Select aria-label="Choose timetable" value={t.id} onChange={(e) => setPicked(e.target.value)}>
        {list.map((x) => <option key={x.id} value={x.id}>{x.name} · {STATUS_TEXT[x.status]}</option>)}
      </Select>
      <div className="flex items-center justify-between gap-2 text-xs text-muted">
        <span>{[t.academic_year, t.term && TERM[t.term]].filter(Boolean).join(" · ") || "All semesters"}</span>
        <TimetableStatusBadge status={t.status} />
      </div>
      <Donut center={`${scheduledPct}%`} sub="Scheduled"
        segments={[
          { label: "Scheduled", value: scheduledPct, color: "var(--ok)" },
          { label: "Unassigned", value: 100 - scheduledPct, color: "var(--warn)" },
        ]} />
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-xl bg-surface-2 py-2"><b className="block text-base tabular-nums">{t.scheduled}/{t.total_sessions}</b><span className="text-muted">Sessions</span></div>
        <div className="rounded-xl bg-surface-2 py-2"><b className="block text-base tabular-nums">{t.quality_score ?? "—"}</b><span className="text-muted">Quality /100</span></div>
        <Tip label="Share of all classroom/lab periods in the week that this timetable uses">
          <div className="rounded-xl bg-surface-2 py-2"><b className="block text-base tabular-nums">{t.room_use_pct ?? "—"}%</b><span className="text-muted">Room use</span></div>
        </Tip>
      </div>
      <Button variant="secondary" className="w-full" icon={<CalendarRange className="size-4" />} onClick={() => navigate(`/timetable?tt=${t.id}`)}>Open this timetable</Button>
    </div>
  );
}

export default function DashboardPage() {
  const { me, can, hasRole } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/dashboard") });
  const seed = useMutation({
    mutationFn: () => api.post("/demo/seed"),
    onSuccess: () => { toast.success("SCSDF data loaded"); void qc.invalidateQueries(); },
  });

  const today = new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  const firstName = me?.full_name.replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s+/i, "").split(" ")[0];
  const empty = data && data.counts.programmes === 0;
  const setup = can("setup.view");

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Welcome back, ${firstName}! Here's what's happening with your timetables.`}
        actions={<>
          <span className="hidden text-sm text-muted sm:inline">{today}</span>
          {can("timetable.generate") && <Button icon={<Plus className="size-4" />} onClick={() => navigate("/generate")}>New timetable</Button>}
        </>}
      />

      {empty && can("setup.edit") && (
        <Card className="mb-5 border-dashed">
          <EmptyState icon={<Sparkles />} title="Let's set up your first timetable"
            description="Add programmes, faculty, rooms and subjects — or load the SCSDF Semester I 2026-27 data to explore every feature."
            action={hasRole("ADMIN") && <Button loading={seed.isPending} onClick={() => seed.mutate()} icon={<Database className="size-4" />}>Load SCSDF data</Button>} />
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {isLoading || !data ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[84px] rounded-2xl" />) : <>
          <StatCard label="Programmes" value={data.counts.programmes} icon={<GraduationCap />} to={setup ? "/programmes" : undefined} hint={`${data.counts.classes} class sections`} />
          <StatCard label="Subjects" value={data.counts.subjects} icon={<BookOpen />} tone="info" to={setup ? "/subjects" : undefined} />
          <StatCard label="Faculty" value={data.counts.faculty} icon={<Users />} tone="gold" to={setup ? "/faculty" : undefined} />
          <StatCard label="Classrooms / Labs" value={data.counts.rooms} icon={<Building2 />} tone="ok" to={setup ? "/rooms" : undefined} hint={`${data.counts.labs} laboratories`} />
        </>}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-5">

        {data?.recent_activity ? (
          <Card className="lg:col-span-3" title="Recent activity" action={can("audit.view") && <Link to="/audit" className="text-xs font-medium text-brand hover:underline">View audit log</Link>}>
            {!data.recent_activity.length ? <p className="py-8 text-center text-sm text-muted">No activity yet.</p> : (
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
          <Card className={can("timetable.view_drafts") ? "lg:col-span-3" : "lg:col-span-5"} title="Your timetable">
            {data?.published ? (
              <div className="flex items-center justify-between gap-4">
                <div><p className="font-semibold">{data.published.name}</p><p className="text-sm text-muted">Published {timeAgo(data.published.published_at)}</p></div>
                <Button icon={<CalendarRange className="size-4" />} onClick={() => navigate("/timetable")}>Open my timetable</Button>
              </div>
            ) : <p className="py-6 text-sm text-muted">No timetable has been published yet.</p>}
          </Card>
        )}

        {/* Scheduling statistics are only meaningful to people who build or review timetables */}
        {can("timetable.view_drafts") && (
          <Card className="lg:col-span-2" title="Timetable overview" description="Pick a published timetable or a draft">
            {!data ? <Skeleton className="h-64" /> : <TimetableOverview list={data.timetables} />}
          </Card>
        )}
      </div>

      {data && (data.last_run !== undefined || data.pending_requests !== undefined || data.users) && (
        <div className="mt-5 grid gap-5 md:grid-cols-3">
          {data.last_run !== undefined && (
            <Card title="Last generation">
              {data.last_run ? (
                <div className="flex items-center justify-between">
                  <div><RunStatusBadge status={data.last_run.status} /><p className="mt-1 text-xs text-muted">{timeAgo(data.last_run.created_at)}</p></div>
                  <Button size="sm" variant="secondary" onClick={() => navigate(`/generate/report/${data.last_run!.id}`)}>View report</Button>
                </div>
              ) : <p className="text-sm text-muted">Not run yet.</p>}
            </Card>
          )}
          {data.pending_requests !== undefined && (
            <Card title="Pending approvals">
              <div className="flex items-center justify-between">
                <p className={cn("text-3xl font-semibold tabular-nums", data.pending_requests ? "text-warn" : "text-ok")}>{data.pending_requests}</p>
                <Button size="sm" variant="secondary" onClick={() => navigate("/requests")}>Review</Button>
              </div>
            </Card>
          )}
          {data.users && (
            <Card title="Active users">
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.users).map(([r, n]) => (
                  <span key={r} className="rounded-lg bg-surface-2 px-2.5 py-1 text-xs"><b className="tabular-nums">{n}</b> {ROLE_LABEL[r as keyof typeof ROLE_LABEL]}</span>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </>
  );
}

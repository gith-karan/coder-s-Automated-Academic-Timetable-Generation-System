import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Building2, CalendarRange, CheckCircle2, Copy, Download, FileSpreadsheet, FileText, GraduationCap, Lock,
  MessageSquareWarning, Printer, RefreshCw, Send, ShieldCheck, Trash2, Unlock, Users,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, downloadUrl, qs, type Violation } from "@/lib/api";
import { useAll } from "@/lib/hooks";
import type { Entry, Faculty, Group, MoveCell, Room, Run, TimetableSummary, TimetableView } from "@/lib/types";
import { cn, DAYS, formatDateTime } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { Button, IconButton } from "@/components/ui/button";
import { Card, EmptyState, PageHeader, Skeleton, Tabs } from "@/components/ui/display";
import { Field, Select, Textarea } from "@/components/ui/form";
import { MenuContent, MenuItem, MenuRoot, MenuSeparator, MenuTrigger, Modal } from "@/components/ui/overlay";
import { TimetableStatusBadge } from "@/components/shared/widgets";
import { TimetableGrid } from "./TimetableGrid";

type View = "group" | "faculty" | "room";

export default function TimetablePage() {
  const { me, hasRole } = useAuth();
  const staff = hasRole("ADMIN", "COORDINATOR");
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const list = useQuery({ queryKey: ["timetables"], queryFn: () => api.get<TimetableSummary[]>("/timetables") });
  const groups = useAll<Group>("groups");
  const faculty = useAll<Faculty>("faculty");
  const rooms = useAll<Room>("rooms");

  const ttId = params.get("tt") ?? (list.data?.find((t) => t.status === "DRAFT" || t.status === "IN_REVIEW") ?? list.data?.find((t) => t.status === "PUBLISHED") ?? list.data?.[0])?.id;
  const defaultView: View = me?.role === "FACULTY" ? "faculty" : "group";
  const view = (params.get("view") as View) ?? defaultView;
  const firstBy = <T,>(xs: T[] | undefined, key: (x: T) => string) => xs?.slice().sort((a, b) => key(a).localeCompare(key(b)))[0];
  const defaultRef = view === "group" ? (me?.group_id ?? firstBy(groups.data, (g) => g.label)?.id)
    : view === "faculty" ? (me?.faculty_id ?? firstBy(faculty.data, (f) => f.name)?.id) : firstBy(rooms.data, (r) => r.code)?.id;
  const ref = params.get("ref") || defaultRef || "";
  const set = (patch: Record<string, string>) => setParams((p) => { const n = new URLSearchParams(p); Object.entries(patch).forEach(([k, v]) => n.set(k, v)); return n; }, { replace: true });

  const data = useQuery({
    queryKey: ["timetable", ttId, view, ref],
    queryFn: () => api.get<TimetableView>(`/timetables/${ttId}${qs({ by: view, ref })}`),
    enabled: !!ttId && !!ref,
  });
  const tt = data.data?.timetable ?? list.data?.find((t) => t.id === ttId);
  const editable = staff && tt?.status === "DRAFT";
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["timetable", ttId] }); void qc.invalidateQueries({ queryKey: ["timetables"] }); };

  const [selected, setSelected] = useState<Entry | null>(null);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [note, setNote] = useState("");
  const [violations, setViolations] = useState<Violation[] | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => setSelected(null), [ttId, view, ref]);

  const move = useMutation({
    mutationFn: ({ e, day, period }: { e: Entry; day: number; period: number }) =>
      api.patch(`/timetables/${ttId}/entries/${e.id}`, { day, start_period: period, expected_version: tt?.row_version }),
    onSuccess: (_d, v) => { toast.success(`${v.e.subject.code} moved to ${DAYS[v.day]} P${v.period + 1}`); refresh(); },
    onError: (e) => { toast.error(e instanceof ApiError ? e.message : "Move rejected"); refresh(); },
    meta: { silent: true },
  });
  const lock = useMutation({
    mutationFn: ({ ids, locked }: { ids: string[]; locked: boolean }) => api.post(`/timetables/${ttId}/lock`, { entry_ids: ids, locked }),
    onSuccess: (_d, v) => { toast.success(v.locked ? `Locked ${v.ids.length} session(s)` : `Unlocked ${v.ids.length} session(s)`); refresh(); },
  });
  const submit = useMutation({
    mutationFn: () => api.post<{ published: boolean }>(`/timetables/${ttId}/submit`, { note }),
    onSuccess: (r) => { toast.success(r.published ? "Timetable published — everyone has been notified" : "Sent to the admin for approval"); setSubmitOpen(false); refresh(); },
    onError: (e) => { if (e instanceof ApiError && e.violations.length) setViolations(e.violations); },
  });
  const duplicate = useMutation({
    mutationFn: () => api.post<TimetableSummary>(`/timetables/${ttId}/duplicate`),
    onSuccess: (t) => { toast.success("Draft copy created"); set({ tt: t.id }); refresh(); },
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/timetables/${ttId}`),
    onSuccess: () => { toast.success("Draft deleted"); setParams({}); refresh(); },
  });

  const validate = async () => {
    const r = await api.get<{ valid: boolean; violations: Violation[] }>(`/timetables/${ttId}/validate`);
    const hard = r.violations.filter((v) => v.severity === "HARD");
    if (r.valid) toast.success(`All mandatory rules satisfied${r.violations.length ? ` · ${r.violations.length} soft preference note(s)` : ""}`);
    else setViolations(hard);
  };

  const regenerate = async () => {
    setRegenerating(true);
    try {
      const { run_id } = await api.post<{ run_id: string }>(`/timetables/${ttId}/generate`, { mode: "unlocked" });
      toast.info("Regenerating unlocked sessions…");
      for (let i = 0; i < 200; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const run = await api.get<Run>(`/runs/${run_id}`);
        if (!["QUEUED", "RUNNING"].includes(run.status)) {
          if (run.status === "SUCCESS") toast.success(`Regenerated · quality ${run.stats.quality?.quality ?? "—"}`);
          else { toast.error("Regeneration could not complete — opening the report"); navigate(`/generate/report/${run_id}`); }
          break;
        }
      }
      refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not regenerate");
    } finally {
      setRegenerating(false);
    }
  };

  const loadOptions = async (e: Entry): Promise<MoveCell[]> => (await api.get<{ cells: MoveCell[] }>(`/timetables/${ttId}/entries/${e.id}/options`)).cells;
  const exportAs = (format: string) => downloadUrl(`/timetables/${ttId}/export${qs({ format, by: view, ref })}`);

  const refOptions = useMemo(() => {
    const byLabel = (a: { label: string }, b: { label: string }) => a.label.localeCompare(b.label);
    if (view === "group") return (groups.data?.map((g) => ({ value: g.id, label: g.label })) ?? []).sort(byLabel);
    if (view === "faculty") return (faculty.data?.map((f) => ({ value: f.id, label: `${f.name} (${f.code})` })) ?? []).sort(byLabel);
    return (rooms.data?.map((r) => ({ value: r.id, label: `${r.code} — ${r.name}` })) ?? []).sort(byLabel);
  }, [view, groups.data, faculty.data, rooms.data]);

  if (list.isLoading) return <Skeleton className="h-[600px]" />;
  if (!list.data?.length || !ttId)
    return (
      <>
        <PageHeader title="Timetable" description="View and manage generated timetables" />
        <Card><EmptyState icon={<CalendarRange />} title="No timetable yet"
          description={staff ? "Generate your first timetable to see it here." : "Your timetable will appear here once it is published."}
          action={staff && <Button onClick={() => navigate("/generate")}>Generate timetable</Button>} /></Card>
      </>
    );

  const entries = data.data?.entries ?? [];
  const visibleIds = entries.map((e) => e.id);
  const iTeach = (e: Entry) => !!me?.faculty_id && e.faculty.some((f) => f.id === me.faculty_id);

  return (
    <>
      <PageHeader title="Timetable" description="View and manage generated timetables"
        actions={
          <div className="no-print flex items-center gap-1.5">
            {editable && <>
              <IconButton label="Lock all visible sessions" variant="secondary" onClick={() => lock.mutate({ ids: visibleIds.filter((id) => !entries.find((e) => e.id === id)?.locked), locked: true })}><Lock className="size-4" /></IconButton>
              <IconButton label="Unlock all visible sessions" variant="secondary" onClick={() => lock.mutate({ ids: visibleIds.filter((id) => entries.find((e) => e.id === id)?.locked), locked: false })}><Unlock className="size-4" /></IconButton>
              <IconButton label="Regenerate unlocked sessions" variant="secondary" loading={regenerating} onClick={regenerate}><RefreshCw className="size-4" /></IconButton>
            </>}
            {staff && <IconButton label="Check all rules" variant="secondary" onClick={validate}><ShieldCheck className="size-4" /></IconButton>}
            <IconButton label="Print" variant="secondary" onClick={() => window.print()}><Printer className="size-4" /></IconButton>
            <MenuRoot>
              <MenuTrigger asChild><Button variant="outline" icon={<Download className="size-4" />}>Export</Button></MenuTrigger>
              <MenuContent>
                <MenuItem icon={<FileText className="size-4" />} onSelect={() => exportAs("pdf")}>PDF (this view)</MenuItem>
                <MenuItem icon={<FileSpreadsheet className="size-4" />} onSelect={() => exportAs("xlsx")}>Excel (this view)</MenuItem>
                <MenuItem icon={<FileText className="size-4" />} onSelect={() => exportAs("csv")}>CSV (this view)</MenuItem>
                <MenuItem icon={<CalendarRange className="size-4" />} onSelect={() => exportAs("ics")}>Calendar file (.ics)</MenuItem>
                {staff && <><MenuSeparator /><MenuItem icon={<FileSpreadsheet className="size-4" />} onSelect={() => downloadUrl(`/timetables/${ttId}/export?format=xlsx`)}>Excel — all classes</MenuItem></>}
              </MenuContent>
            </MenuRoot>
            {staff && tt?.status === "DRAFT" && (
              <Button icon={<Send className="size-4" />} onClick={() => setSubmitOpen(true)}>{hasRole("ADMIN") ? "Publish" : "Send for review"}</Button>
            )}
            {staff && tt && tt.status !== "DRAFT" && <IconButton label="Duplicate as new draft" variant="secondary" onClick={() => duplicate.mutate()}><Copy className="size-4" /></IconButton>}
            {staff && tt?.status === "DRAFT" && <IconButton label="Delete draft" variant="secondary" className="hover:text-bad" onClick={() => setConfirmDelete(true)}><Trash2 className="size-4" /></IconButton>}
          </div>
        } />

      <Card className="[&>div]:p-0">
        <div className="no-print flex flex-wrap items-center gap-3 border-b border-line px-4 pt-3">
          <Tabs value={view} onValueChange={(v) => set({ view: v, ref: "" })} className="-mb-px"
            tabs={[
              { value: "group", label: "Programme view", icon: <GraduationCap className="size-4" /> },
              { value: "faculty", label: "Faculty view", icon: <Users className="size-4" /> },
              { value: "room", label: "Room / Lab view", icon: <Building2 className="size-4" /> },
            ]} />
        </div>
        <div className="no-print flex flex-wrap items-end gap-3 px-4 py-3">
          {(staff || list.data.length > 1) && (
            <Field label="Timetable" className="w-72">
              <Select value={ttId} onChange={(e) => set({ tt: e.target.value })}>
                {list.data.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.status.toLowerCase().replace("_", " ")}</option>)}
              </Select>
            </Field>
          )}
          <Field label={view === "group" ? "Class" : view === "faculty" ? "Faculty member" : "Room"} className="w-72">
            <Select value={ref} onChange={(e) => set({ ref: e.target.value })}>
              {refOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </Field>
          {tt && (
            <div className="ml-auto flex items-center gap-3 text-xs text-muted">
              <TimetableStatusBadge status={tt.status} />
              {tt.quality_score != null && <span>Quality <b className="text-ink">{tt.quality_score}</b></span>}
              <span><b className="text-ink">{tt.scheduled}</b>/{tt.total_sessions} placed</span>
              {tt.locked > 0 && <span className="inline-flex items-center gap-1"><Lock className="size-3" />{tt.locked}</span>}
            </div>
          )}
        </div>

        {tt?.status === "IN_REVIEW" && <p className="mx-4 mb-3 flex items-center gap-2 rounded-xl bg-warn/10 px-3 py-2 text-sm text-warn"><Send className="size-4" />Awaiting admin approval since {formatDateTime(tt.submitted_at)}. Editing is paused.</p>}
        {tt?.status === "DRAFT" && tt.review_comment && <p className="mx-4 mb-3 flex items-center gap-2 rounded-xl bg-bad/10 px-3 py-2 text-sm text-bad"><MessageSquareWarning className="size-4" />Returned by admin: “{tt.review_comment}”</p>}
        {tt?.status === "DRAFT" && !tt.is_complete && tt.total_sessions > 0 && <p className="mx-4 mb-3 flex items-center gap-2 rounded-xl bg-warn/10 px-3 py-2 text-sm text-warn"><AlertTriangle className="size-4" />This draft is incomplete or has conflicts and cannot be published yet.</p>}
        {editable && <p className="no-print mx-4 mb-3 text-xs text-muted">Drag a session to move it — cells turn green (allowed), amber (allowed, less preferred) or red (breaks a rule). Click the lock icon to keep a session in place when regenerating.</p>}

        <div className="px-4 pb-4">
          <p className="mb-2 hidden text-sm font-semibold print:block">{tt?.name} — {refOptions.find((o) => o.value === ref)?.label}</p>
          {data.isLoading || !data.data ? <Skeleton className="h-[520px]" /> : (
            <TimetableGrid grid={data.data.grid} entries={entries} unassigned={editable ? data.data.unassigned : []} editable={!!editable}
              loadOptions={editable ? loadOptions : undefined}
              onMove={(e, day, period) => move.mutate({ e, day, period })}
              onToggleLock={editable ? (e) => lock.mutate({ ids: [e.id], locked: !e.locked }) : undefined}
              onEntryClick={setSelected} />
          )}
          {data.data && entries.length === 0 && <p className="py-6 text-center text-sm text-muted">No sessions for this selection.</p>}
        </div>
      </Card>

      <SessionDetails entry={selected} onClose={() => setSelected(null)} grid={data.data?.grid} ttId={ttId}
        canRequest={me?.role === "FACULTY" && tt?.status === "PUBLISHED" && !!selected && iTeach(selected)} />

      <Modal open={submitOpen} onOpenChange={setSubmitOpen} title={hasRole("ADMIN") ? "Publish timetable" : "Send for admin review"}
        description={hasRole("ADMIN") ? "Every rule is re-checked before publishing. Faculty and students are notified." : "The admin reviews and publishes it. You will be notified of the decision."}
        footer={<><Button variant="secondary" onClick={() => setSubmitOpen(false)}>Cancel</Button>
          <Button loading={submit.isPending} icon={<Send className="size-4" />} onClick={() => submit.mutate()}>{hasRole("ADMIN") ? "Publish" : "Send for review"}</Button></>}>
        <Field label="Note (optional)"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Final version for Odd Semester 2026-27" maxLength={500} /></Field>
      </Modal>

      <Modal open={confirmDelete} onOpenChange={setConfirmDelete} size="sm" title="Delete this draft?"
        description="Published timetables are never deleted; this only removes the draft. The action is audited."
        footer={<><Button variant="secondary" onClick={() => setConfirmDelete(false)}>Cancel</Button>
          <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate(undefined, { onSuccess: () => setConfirmDelete(false) })}>Delete draft</Button></>}>
        <p className="text-sm text-muted">{tt?.name}</p>
      </Modal>

      <Modal open={!!violations} onOpenChange={(o) => !o && setViolations(null)} title="Rules that are not yet satisfied" size="lg"
        footer={<Button onClick={() => setViolations(null)}>Close</Button>}>
        <ul className="space-y-2">
          {violations?.map((v, i) => (
            <li key={i} className="flex items-start gap-2 text-sm"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />{v.message}</li>
          ))}
          {violations?.length === 0 && <li className="flex items-center gap-2 text-sm text-ok"><CheckCircle2 className="size-4" />No problems.</li>}
        </ul>
      </Modal>
    </>
  );
}

function SessionDetails({ entry, onClose, grid, ttId, canRequest }: {
  entry: Entry | null; onClose: () => void; grid?: TimetableView["grid"]; ttId: string; canRequest: boolean;
}) {
  const [day, setDay] = useState(0);
  const [period, setPeriod] = useState(0);
  const [reason, setReason] = useState("");
  const req = useMutation({
    mutationFn: () => api.post(`/timetables/${ttId}/move-requests`, { entry_id: entry!.id, day, start_period: period, reason }),
    onSuccess: () => { toast.success("Change request sent to the coordinator"); onClose(); },
  });
  if (!entry) return null;
  const p0 = grid?.days.find((d) => d.day === entry.day)?.periods[entry.start_period ?? 0];
  const p1 = grid?.days.find((d) => d.day === entry.day)?.periods[(entry.start_period ?? 0) + entry.length - 1];
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={`${entry.subject.code} — ${entry.subject.name}`}
      description={`${entry.subject.kind === "PRACTICAL" ? "Practical" : "Theory"} · ${entry.group.label}${entry.batch ? ` / ${entry.batch.name}` : ""}`}
      footer={canRequest ? <><Button variant="secondary" onClick={onClose}>Close</Button>
        <Button loading={req.isPending} icon={<Send className="size-4" />} onClick={() => req.mutate()}>Request change</Button></> : <Button onClick={onClose}>Close</Button>}>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-xs text-muted">When</dt><dd className="font-medium">{entry.day != null ? `${DAYS[entry.day]}, ${p0?.start}–${p1?.end}` : "Unassigned"}</dd></div>
        <div><dt className="text-xs text-muted">Room</dt><dd className="font-medium">{entry.room ? `${entry.room.code} · ${entry.room.name}` : "—"}</dd></div>
        <div className="col-span-2"><dt className="text-xs text-muted">Faculty</dt><dd className="font-medium">{entry.faculty.map((f) => f.name).join(", ")}</dd></div>
        <div><dt className="text-xs text-muted">Status</dt><dd className={cn("font-medium", entry.locked && "text-brand")}>{entry.locked ? "Locked" : "Movable"}</dd></div>
      </dl>
      {canRequest && grid && (
        <div className="mt-5 space-y-3 border-t border-line pt-4">
          <p className="text-sm font-semibold">Request a different slot</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Day"><Select value={day} onChange={(e) => setDay(Number(e.target.value))}>{grid.days.map((d) => <option key={d.day} value={d.day}>{d.name}</option>)}</Select></Field>
            <Field label="Starting period"><Select value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
              {(grid.days.find((d) => d.day === day)?.periods ?? []).map((p) => <option key={p.index} value={p.index}>P{p.index + 1} · {p.start}</option>)}</Select></Field>
          </div>
          <Textarea placeholder="Reason (shown to the coordinator)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          <p className="text-xs text-muted">The system checks the new slot for clashes before sending.</p>
        </div>
      )}
    </Modal>
  );
}

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, ChevronLeft, ChevronRight, Cpu, Loader2, Sparkles, Square, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, qs } from "@/lib/api";
import { useAll } from "@/lib/hooks";
import type { Programme, Readiness, TimetableSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, PageHeader, Progress, Skeleton } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { DiagnosticList, TimetableStatusBadge } from "@/components/shared/widgets";

const STEPS = ["Select settings", "Review", "Generate", "Results"];

interface ProgressEvent { event: string; phase?: string; message?: string; placed?: number; total?: number; solutions?: number; elapsed_s?: number; status?: string; objective?: number }

function Stepper({ step }: { step: number }) {
  return (
    <ol className="mb-6 flex items-center gap-2">
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-1 items-center gap-2">
          <span className={cn("grid size-7 shrink-0 place-items-center rounded-full border text-xs font-semibold",
            i < step ? "border-brand bg-brand text-white" : i === step ? "border-brand text-brand" : "border-line text-muted")}>
            {i < step ? <Check className="size-3.5" /> : i + 1}
          </span>
          <span className={cn("hidden text-sm sm:inline", i === step ? "font-semibold" : "text-muted")}>{s}</span>
          {i < STEPS.length - 1 && <span className={cn("h-px flex-1", i < step ? "bg-brand" : "bg-line")} />}
        </li>
      ))}
    </ol>
  );
}

export default function GeneratePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const programmes = useAll<Programme>("programmes");
  const timetables = useQuery({ queryKey: ["timetables"], queryFn: () => api.get<TimetableSummary[]>("/timetables") });
  const drafts = timetables.data?.filter((t) => t.status === "DRAFT") ?? [];

  const [target, setTarget] = useState<string>("new");
  const now = new Date();
  const y = now.getMonth() >= 5 ? now.getFullYear() : now.getFullYear() - 1; // academic year starts in June/July
  const [year, setYear] = useState(`${y}-${String((y + 1) % 100).padStart(2, "0")}`);
  const [term, setTerm] = useState<"ODD" | "EVEN">(now.getMonth() >= 5 ? "ODD" : "EVEN");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [dupSuggestion, setDupSuggestion] = useState<string | null>(null);
  const [programmeId, setProgrammeId] = useState("");
  const [semester, setSemester] = useState("");
  const [mode, setMode] = useState<"full" | "unlocked">("full");
  const autoName = `${term === "ODD" ? "Odd" : "Even"} Semester ${year}`;
  const finalName = nameTouched ? name : autoName;
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [final, setFinal] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const touched = useRef(false);
  // Default to the most recent draft once, without overriding the user's own choice.
  useEffect(() => { if (!touched.current && drafts.length) { touched.current = true; setTarget(drafts[0].id); } }, [drafts]);
  useEffect(() => () => esRef.current?.close(), []);

  const scope = { programme_ids: programmeId ? [programmeId] : [], semesters: semester ? [Number(semester)] : [] };
  const draftTerm = drafts.find((d) => d.id === target)?.term ?? null;
  const readinessTerm = target === "new" ? term : draftTerm;
  const readiness = useQuery({
    queryKey: ["readiness", scope, readinessTerm, target],
    queryFn: () => api.get<Readiness>(`/readiness${qs({ programme_ids: scope.programme_ids, semesters: scope.semesters, term: readinessTerm ?? undefined })}`),
    enabled: step >= 1,
  });
  const selectedProgramme = programmes.data?.find((p) => p.id === programmeId);

  const start = async (nameOverride?: string) => {
    try {
      let tid = target;
      if (target === "new") {
        try {
          const tt = await api.post<TimetableSummary>("/timetables", { name: nameOverride ?? finalName, academic_year: year, term, ...scope });
          tid = tt.id;
          setTarget(tid);
          setDupSuggestion(null);
        } catch (e) {
          if (e instanceof ApiError && e.code === "duplicate_name") {
            setDupSuggestion(String(e.body.suggestion));
            setStep(0);
            return;
          }
          throw e;
        }
      }
      const r = await api.post<{ run_id: string }>(`/timetables/${tid}/generate`, { mode });
      setRunId(r.run_id);
      setEvents([]);
      setFinal(null);
      setStep(2);
      const es = new EventSource(`/api/v1/runs/${r.run_id}/events`);
      esRef.current = es;
      es.onmessage = (m) => {
        const ev = JSON.parse(m.data) as ProgressEvent;
        setEvents((xs) => [...xs, ev]);
        if (ev.event === "done") {
          es.close();
          setFinal(ev.status ?? "FAILED");
          void qc.invalidateQueries({ queryKey: ["timetables"] });
          void qc.invalidateQueries({ queryKey: ["dashboard"] });
          setTimeout(() => navigate(`/generate/report/${r.run_id}`), 900);
        }
      };
      es.onerror = () => { /* EventSource retries automatically; final state is also available via the report page */ };
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not start generation");
    }
  };

  const cancel = async () => { if (runId) await api.post(`/runs/${runId}/cancel`).catch(() => undefined); };

  const last = [...events].reverse();
  const phase = last.find((e) => e.event === "phase");
  const sol = last.find((e) => e.event === "solution");
  const total = last.find((e) => e.total)?.total ?? sol?.total;

  return (
    <>
      <PageHeader title="Generate Timetable" description="Create a conflict-free timetable from your inputs in four steps" />
      <Card className="mx-auto max-w-3xl">
        <Stepper step={final ? 3 : step} />

        {step === 0 && (
          <div className="space-y-5">
            <Field label="Timetable">
              <Select value={target} onChange={(e) => { touched.current = true; setTarget(e.target.value); }}>
                <option value="new">➕ Create a new draft</option>
                {drafts.map((d) => <option key={d.id} value={d.id}>{d.name} (draft, {d.scheduled}/{d.total_sessions} placed)</option>)}
              </Select>
            </Field>
            {target === "new" ? (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Academic year" hint="Format 2026-27">
                    <Input value={year} maxLength={7} onChange={(e) => setYear(e.target.value)} placeholder="2026-27" />
                  </Field>
                  <Field label="Term" hint={term === "ODD" ? "Schedules Semesters I, III, V, VII, IX" : "Schedules Semesters II, IV, VI, VIII, X"}>
                    <Select value={term} onChange={(e) => { setTerm(e.target.value as "ODD" | "EVEN"); setSemester(""); }}>
                      <option value="ODD">Odd term (July – December)</option>
                      <option value="EVEN">Even term (January – May)</option>
                    </Select>
                  </Field>
                </div>
                <Field label="Timetable name">
                  <Input value={finalName} onChange={(e) => { setNameTouched(true); setName(e.target.value); setDupSuggestion(null); }} />
                </Field>
                {dupSuggestion && (
                  <div className="flex flex-wrap items-center gap-2 rounded-xl border border-warn/40 bg-warn/10 p-3 text-sm">
                    <span className="flex-1">A timetable named <b>{finalName}</b> already exists. Use <b>{dupSuggestion}</b> instead, or type a different name.</span>
                    <Button size="sm" onClick={() => { setNameTouched(true); setName(dupSuggestion); setDupSuggestion(null); }}>Use “{dupSuggestion}”</Button>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Programme" help="Leave “All programmes” to schedule everything together. This is recommended because programmes share faculty and rooms, and scheduling them together avoids clashes between them.">
                    <Select value={programmeId} onChange={(e) => { setProgrammeId(e.target.value); setSemester(""); }}>
                      <option value="">All programmes</option>
                      {programmes.data?.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
                    </Select>
                  </Field>
                  <Field label="Semester">
                    <Select value={semester} onChange={(e) => setSemester(e.target.value)} disabled={!selectedProgramme}>
                      <option value="">All {term === "ODD" ? "odd" : "even"} semesters</option>
                      {selectedProgramme && Array.from({ length: selectedProgramme.duration_semesters }, (_, i) => i + 1)
                        .filter((n) => (term === "ODD" ? n % 2 === 1 : n % 2 === 0))
                        .map((n) => <option key={n} value={n}>Semester {n}</option>)}
                    </Select>
                  </Field>
                </div>
              </>
            ) : (
              <div className="flex items-center gap-2 rounded-xl bg-surface-2 p-3 text-sm">
                <TimetableStatusBadge status="DRAFT" /> Regenerating an existing draft keeps its locked sessions.
              </div>
            )}
            <Field label="Generation mode" help="No time setting is needed: the engine finds a valid timetable within seconds, keeps improving it, and stops by itself as soon as it has proven it is the best possible one.">
              <div className="grid gap-2 sm:grid-cols-2">
                {([["full", "Auto (recommended)", "Build the best timetable from scratch. Locked sessions stay."],
                   ["unlocked", "Keep current layout", "Regenerate unlocked sessions while moving as few as possible."]] as const).map(([v, t, d]) => (
                  <button key={v} type="button" onClick={() => setMode(v)} aria-pressed={mode === v}
                    className={cn("rounded-xl border p-3 text-left transition-colors", mode === v ? "border-brand bg-brand/5 ring-1 ring-brand/30" : "border-line hover:bg-surface-2")}>
                    <p className="text-sm font-semibold">{t}</p><p className="text-xs text-muted">{d}</p>
                  </button>
                ))}
              </div>
            </Field>
            <div className="flex justify-end"><Button onClick={() => setStep(1)} disabled={target === "new" && !/^20\d{2}-\d{2}$/.test(year)} icon={<ChevronRight className="size-4" />}>Next</Button></div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            {!readiness.data ? <Skeleton className="h-48" /> : (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {([["Sessions", readiness.data.counts.sessions], ["Classes", readiness.data.counts.classes], ["Faculty", readiness.data.counts.faculty],
                     ["Periods / week", readiness.data.counts.periods_per_week]] as const).map(([l, v]) => (
                    <div key={l} className="rounded-xl bg-surface-2 p-3 text-center"><p className="text-xl font-semibold tabular-nums">{v}</p><p className="text-xs text-muted">{l}</p></div>
                  ))}
                </div>
                <div className={cn("flex items-center gap-2 rounded-xl p-3 text-sm font-medium", readiness.data.ready ? "bg-ok/10 text-ok" : "bg-bad/10 text-bad")}>
                  {readiness.data.ready ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
                  {readiness.data.ready ? "All pre-flight checks passed. Ready to generate." : "Some inputs make a complete timetable impossible. Fix them first."}
                </div>
                <DiagnosticList items={readiness.data.diagnostics} empty={<p className="text-sm text-muted">{readiness.data.ready ? "No warnings." : "Nothing to schedule for this selection."}</p>} />
              </>
            )}
            <div className="flex justify-between">
              <Button variant="secondary" icon={<ChevronLeft className="size-4" />} onClick={() => setStep(0)}>Back</Button>
              <Button icon={<Sparkles className="size-4" />} disabled={!readiness.data?.counts.sessions} onClick={() => void start()}>
                {readiness.data?.ready ? "Generate" : "Generate anyway"}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6 py-4 text-center">
            <div className="mx-auto grid size-20 place-items-center rounded-3xl bg-brand/10 text-brand">
              {final ? (final === "SUCCESS" ? <CheckCircle2 className="size-10 text-ok" /> : <XCircle className="size-10 text-bad" />) : <Cpu className="size-10 animate-pulse" />}
            </div>
            <div>
              <p className="text-lg font-semibold">{final ? (final === "SUCCESS" ? "Timetable generated!" : "Finished — see the report") : phase?.message ?? "Starting…"}</p>
              <p className="text-sm text-muted">
                {sol ? `${sol.solutions} solution${sol.solutions === 1 ? "" : "s"} found · ${sol.elapsed_s}s` : "The constraint solver is exploring arrangements…"}
              </p>
            </div>
            {total ? <div className="mx-auto max-w-md"><Progress value={((sol?.placed ?? 0) / total) * 100} tone={final && final !== "SUCCESS" ? "bad" : "brand"} />
              <p className="mt-1 text-xs text-muted">{sol?.placed ?? 0} / {total} sessions placed</p></div> : null}
            <ul className="mx-auto max-w-md space-y-1 text-left text-xs text-muted">
              {events.filter((e) => e.event === "phase").map((e, i) => (
                <li key={i} className="flex items-center gap-2"><Check className="size-3.5 text-ok" />{e.message}</li>
              ))}
              {!final && <li className="flex items-center gap-2"><Loader2 className="size-3.5 animate-spin" />Working…</li>}
            </ul>
            {!final && <Button variant="secondary" icon={<Square className="size-4" />} onClick={cancel}>Cancel</Button>}
          </div>
        )}
      </Card>
    </>
  );
}

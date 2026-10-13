import { Fragment, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Fingerprint, Search, ShieldCheck, ShieldX } from "lucide-react";
import { api, qs } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { AuditRow, Paged } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge, Card, PageHeader, Skeleton } from "@/components/ui/display";
import { Input, Select } from "@/components/ui/form";
import { Pagination } from "@/components/ui/table";

const OUTCOME_TONE = { SUCCESS: "ok", FAILURE: "bad", DENIED: "warn" } as const;

export default function AuditPage() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [outcome, setOutcome] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const dq = useDebounced(q);
  const { data, isLoading } = useQuery({
    queryKey: ["audit", dq, category, outcome, page],
    queryFn: () => api.get<Paged<AuditRow>>(`/audit-logs${qs({ q: dq, category, outcome, page, size: 25 })}`),
  });
  const verify = useMutation({ mutationFn: () => api.get<{ ok: boolean; checked: number; message: string }>("/audit-logs/verify") });

  return (
    <>
      <PageHeader title="Audit Log" description="Every sign-in, change, approval and denied action — append-only and tamper-evident"
        actions={<Button variant="outline" icon={<Fingerprint className="size-4" />} loading={verify.isPending} onClick={() => verify.mutate()}>Verify integrity</Button>} />
      {verify.data && (
        <div role="status" className={cn("mb-4 flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm font-medium",
          verify.data.ok ? "border-ok/30 bg-ok/10 text-ok" : "border-bad/30 bg-bad/10 text-bad")}>
          {verify.data.ok ? <ShieldCheck className="size-5" /> : <ShieldX className="size-5" />}{verify.data.message}
        </div>
      )}
      <Card className="[&>div]:p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-4">
          <div className="w-full max-w-xs"><Input icon={<Search />} placeholder="Search actions, users, details…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search audit log" /></div>
          <Select aria-label="Category" className="w-40" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
            <option value="">All categories</option>{["AUTH", "USER", "DATA", "TIMETABLE", "WORKFLOW", "SECURITY", "SYSTEM"].map((c) => <option key={c}>{c}</option>)}
          </Select>
          <Select aria-label="Outcome" className="w-36" value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1); }}>
            <option value="">All outcomes</option>{["SUCCESS", "FAILURE", "DENIED"].map((c) => <option key={c}>{c}</option>)}
          </Select>
        </div>
        {isLoading ? <div className="p-4"><Skeleton className="h-80" /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-xs text-muted">
                <th className="w-8" /><th className="px-3 py-3 font-medium">#</th><th className="px-3 py-3 font-medium">When</th><th className="px-3 py-3 font-medium">Who</th>
                <th className="px-3 py-3 font-medium">Event</th><th className="px-3 py-3 font-medium">Outcome</th><th className="hidden px-3 py-3 font-medium md:table-cell">IP</th>
              </tr></thead>
              <tbody>
                {data?.items.map((r) => (
                  <Fragment key={r.seq}>
                    <tr className="cursor-pointer border-b border-line/60 hover:bg-surface-2" onClick={() => setOpen(open === r.seq ? null : r.seq)}>
                      <td className="pl-3 text-muted">{open === r.seq ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-muted">{r.seq}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-xs">{formatDateTime(r.at)}</td>
                      <td className="px-3 py-2.5 text-xs"><span className="block">{r.actor_email ?? "—"}</span><span className="text-muted">{r.actor_role ?? ""}</span></td>
                      <td className="px-3 py-2.5"><span className="block">{r.summary}</span><span className="font-mono text-[11px] text-muted">{r.category} · {r.action}</span></td>
                      <td className="px-3 py-2.5"><Badge tone={OUTCOME_TONE[r.outcome as keyof typeof OUTCOME_TONE] ?? "neutral"}>{r.outcome}</Badge></td>
                      <td className="hidden px-3 py-2.5 font-mono text-xs text-muted md:table-cell">{r.ip ?? "—"}</td>
                    </tr>
                    {open === r.seq && (
                      <tr className="border-b border-line/60 bg-surface-2">
                        <td colSpan={7} className="px-6 py-3">
                          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-[11px]">{JSON.stringify(r.data, null, 2)}</pre>
                          <p className="mt-2 font-mono text-[10px] text-muted">request {r.request_id ?? "—"} · chain hash {r.hash}</p>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={page} size={data.size} total={data.total} onPage={setPage} />}
      </Card>
    </>
  );
}

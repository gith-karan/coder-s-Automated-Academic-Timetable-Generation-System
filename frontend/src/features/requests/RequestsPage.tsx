import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Check, ClipboardCheck, MoveRight, Send, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { ChangeRequest } from "@/lib/types";
import { DAYS, ROLE_LABEL, timeAgo } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, PageHeader, Skeleton, Tabs } from "@/components/ui/display";
import { Textarea } from "@/components/ui/form";
import { Modal } from "@/components/ui/overlay";

const KIND = {
  AVAILABILITY: { label: "Availability change", icon: CalendarDays },
  SESSION_MOVE: { label: "Session move", icon: MoveRight },
  TIMETABLE_PUBLISH: { label: "Publish timetable", icon: Send },
} as const;
const STATUS_TONE = { PENDING: "warn", APPROVED: "ok", REJECTED: "bad", CANCELLED: "neutral" } as const;

export default function RequestsPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const reviewer = me?.role === "ADMIN" || me?.role === "COORDINATOR";
  const [tab, setTab] = useState(reviewer ? "PENDING" : "mine");
  const { data, isLoading } = useQuery({
    queryKey: ["requests", tab],
    queryFn: () => api.get<ChangeRequest[]>(tab === "mine" ? "/requests?mine=true" : tab === "PENDING" ? "/requests?status=PENDING" : "/requests"),
  });
  const [deciding, setDeciding] = useState<{ r: ChangeRequest; approve: boolean } | null>(null);
  const [comment, setComment] = useState("");
  const review = useMutation({
    mutationFn: () => api.post(`/requests/${deciding!.r.id}/review`, { approve: deciding!.approve, comment }),
    onSuccess: () => { toast.success(deciding!.approve ? "Approved" : "Rejected"); setDeciding(null); setComment(""); void qc.invalidateQueries(); },
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.post(`/requests/${id}/cancel`),
    onSuccess: () => { toast.success("Request cancelled"); void qc.invalidateQueries({ queryKey: ["requests"] }); },
  });

  const tabs = reviewer
    ? [{ value: "PENDING", label: "Awaiting decision" }, { value: "all", label: "All requests" }, { value: "mine", label: "My requests" }]
    : [{ value: "mine", label: "My requests" }];

  return (
    <>
      <PageHeader title="Approvals" description="Changes that need a higher role's approval before they take effect" />
      <Card>
        <Tabs value={tab} onValueChange={setTab} tabs={tabs} />
        <div className="pt-4">
          {isLoading ? <Skeleton className="h-40" /> : !data?.length ? (
            <EmptyState icon={<ClipboardCheck />} title={tab === "PENDING" ? "Nothing waiting for you" : "No requests"} description="Requests appear here when faculty or coordinators ask for a change." />
          ) : (
            <ul className="space-y-3">
              {data.map((r) => {
                const K = KIND[r.kind];
                const canDecide = reviewer && r.status === "PENDING" && r.requested_by?.id !== me?.id &&
                  (r.reviewer_role !== "ADMIN" || me?.role === "ADMIN");
                const to = r.payload.to as number[] | undefined;
                const from = r.payload.from as number[] | undefined;
                return (
                  <li key={r.id} className="rounded-2xl border border-line p-4">
                    <div className="flex flex-wrap items-start gap-3">
                      <div className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand"><K.icon className="size-5" /></div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium">{r.title}</p>
                          <Badge tone={STATUS_TONE[r.status]}>{r.status.toLowerCase()}</Badge>
                          <Badge>{K.label}</Badge>
                        </div>
                        <p className="mt-0.5 text-xs text-muted">
                          {r.requested_by?.name} ({r.requested_by && ROLE_LABEL[r.requested_by.role]}) · {timeAgo(r.created_at)} · needs {ROLE_LABEL[r.reviewer_role]} approval
                        </p>
                        {r.reason && <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-sm">“{r.reason}”</p>}
                        {r.kind === "SESSION_MOVE" && from && to && (
                          <p className="mt-2 text-sm">{DAYS[from[0]]} P{from[1] + 1} <MoveRight className="inline size-4 text-muted" /> <b>{DAYS[to[0]]} P{to[1] + 1}</b></p>
                        )}
                        {r.kind === "TIMETABLE_PUBLISH" && <Link to={`/timetable?tt=${r.target_id}`} className="mt-2 inline-block text-sm font-medium text-brand hover:underline">Open timetable →</Link>}
                        {r.review_comment && <p className="mt-2 text-xs text-muted">Reviewer: “{r.review_comment}” — {r.reviewed_by?.name}</p>}
                        {typeof r.payload.draft_id === "string" && <Link to={`/timetable?tt=${r.payload.draft_id}`} className="mt-1 inline-block text-xs font-medium text-brand hover:underline">Open the revised draft →</Link>}
                      </div>
                      <div className="flex gap-2">
                        {canDecide && <>
                          <Button size="sm" variant="secondary" icon={<X className="size-4" />} onClick={() => setDeciding({ r, approve: false })}>Reject</Button>
                          <Button size="sm" icon={<Check className="size-4" />} onClick={() => setDeciding({ r, approve: true })}>Approve</Button>
                        </>}
                        {r.status === "PENDING" && r.requested_by?.id === me?.id && (
                          <Button size="sm" variant="ghost" loading={cancel.isPending} onClick={() => cancel.mutate(r.id)}>Cancel</Button>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>

      <Modal open={!!deciding} onOpenChange={(o) => !o && setDeciding(null)} size="sm"
        title={deciding?.approve ? "Approve request" : "Reject request"} description={deciding?.r.title}
        footer={<><Button variant="secondary" onClick={() => setDeciding(null)}>Cancel</Button>
          <Button variant={deciding?.approve ? "primary" : "danger"} loading={review.isPending} disabled={!deciding?.approve && !comment.trim()} onClick={() => review.mutate()}>
            {deciding?.approve ? "Approve" : "Reject"}</Button></>}>
        <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500}
          placeholder={deciding?.approve ? "Comment (optional)" : "Reason for rejecting (required — the requester will see it)"} />
      </Modal>
    </>
  );
}

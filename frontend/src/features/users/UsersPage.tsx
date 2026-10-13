import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, MoreHorizontal, Plus, Search, ShieldAlert, UserCheck, UserCog, UserX } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, qs } from "@/lib/api";
import { useAll, useDebounced } from "@/lib/hooks";
import type { Faculty, Group, Paged, Role, UserRow } from "@/lib/types";
import { initials, ROLE_LABEL, timeAgo } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, PageHeader } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { MenuContent, MenuItem, MenuRoot, MenuTrigger, Modal } from "@/components/ui/overlay";
import { DataTable, Pagination } from "@/components/ui/table";

const ROLE_TONE = { ADMIN: "bad", COORDINATOR: "brand", FACULTY: "info", STUDENT: "neutral" } as const;
const WHO_IS_NOTIFIED: Record<Role, string> = {
  ADMIN: "Other admins are notified.",
  COORDINATOR: "Admins are notified about this new user.",
  FACULTY: "Coordinators and admins are notified about this new user.",
  STUDENT: "",
};

export default function UsersPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const creatable = (me?.permissions ?? []).filter((p) => p.startsWith("create:")).map((p) => p.slice(7) as Role);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const list = useQuery({ queryKey: ["users", dq, role, page], queryFn: () => api.get<Paged<UserRow>>(`/users${qs({ q: dq, role, page, size: 10 })}`) });
  const faculty = useAll<Faculty>("faculty", {}, creatable.includes("FACULTY"));
  const groups = useAll<Group>("groups", {}, creatable.includes("STUDENT"));

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", role: creatable[creatable.length - 1] ?? "STUDENT", faculty_id: "", enrollment_no: "", group_id: "", batch_id: "" });
  const [secret, setSecret] = useState<{ email: string; password: string } | null>(null);

  const create = useMutation({
    mutationFn: () => api.post<UserRow & { temporary_password: string }>("/users", {
      full_name: form.full_name, email: form.email, role: form.role,
      faculty_id: form.role === "FACULTY" ? form.faculty_id || null : null,
      enrollment_no: form.role === "STUDENT" ? form.enrollment_no || null : null,
      group_id: form.role === "STUDENT" ? form.group_id || null : null,
      batch_id: form.role === "STUDENT" ? form.batch_id || null : null,
    }),
    onSuccess: (u) => { setOpen(false); setSecret({ email: u.email, password: u.temporary_password }); void qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? (e.errors[0]?.message ?? e.message) : "Could not create user"),
    meta: { silent: true },
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: unknown }) => api.patch(`/users/${id}`, body),
    onSuccess: () => { toast.success("User updated"); void qc.invalidateQueries({ queryKey: ["users"] }); },
  });
  const reset = useMutation({
    mutationFn: (u: UserRow) => api.post<{ temporary_password: string }>(`/users/${u.id}/reset-password`).then((r) => ({ email: u.email, password: r.temporary_password })),
    onSuccess: setSecret,
  });

  const grp = groups.data?.find((g) => g.id === form.group_id);

  return (
    <>
      <PageHeader title="Users" description={me?.role === "FACULTY" ? "Students you have added" : "Manage who can access the timetable system"}
        actions={creatable.length > 0 && <Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>Add user</Button>} />
      <Card className="[&>div]:p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-4">
          <div className="w-full max-w-xs"><Input icon={<Search />} placeholder="Search name or email…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search users" /></div>
          {me?.role !== "FACULTY" && (
            <Select aria-label="Filter by role" className="w-40" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }}>
              <option value="">All roles</option>
              {(["ADMIN", "COORDINATOR", "FACULTY", "STUDENT"] as Role[]).filter((r) => me?.role === "ADMIN" || creatable.includes(r)).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
          )}
        </div>
        <DataTable rows={list.data?.items} loading={list.isLoading}
          empty={<EmptyState icon={<UserCog />} title="No users found" />}
          columns={[
            { key: "n", header: "Name", cell: (u) => (
              <span className="flex items-center gap-2.5">
                <span className="grid size-8 place-items-center rounded-full bg-brand/10 text-[11px] font-bold text-brand">{initials(u.full_name)}</span>
                <span><span className="block font-medium">{u.full_name}</span><span className="block text-xs text-muted">{u.email}</span></span>
              </span>) },
            { key: "r", header: "Role", cell: (u) => <Badge tone={ROLE_TONE[u.role]}>{ROLE_LABEL[u.role]}</Badge> },
            { key: "s", header: "Status", cell: (u) => !u.is_active ? <Badge>Deactivated</Badge> : u.must_change_password ? <Badge tone="warn">Invited</Badge> : <Badge tone="ok">Active</Badge>, hideOnMobile: true },
            { key: "b", header: "Added by", cell: (u) => <span className="text-xs text-muted">{u.created_by?.full_name ?? "System"}</span>, hideOnMobile: true },
            { key: "l", header: "Last sign-in", cell: (u) => <span className="text-xs text-muted">{timeAgo(u.last_login_at)}</span>, hideOnMobile: true },
            { key: "a", header: <span className="sr-only">Actions</span>, className: "w-12", cell: (u) => u.id === me?.id ? null : (
              <MenuRoot>
                <MenuTrigger asChild><button aria-label={`Actions for ${u.full_name}`} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-line/60"><MoreHorizontal className="size-4" /></button></MenuTrigger>
                <MenuContent>
                  <MenuItem icon={<KeyRound className="size-4" />} onSelect={() => reset.mutate(u)}>Reset password</MenuItem>
                  {u.is_active
                    ? <MenuItem danger icon={<UserX className="size-4" />} onSelect={() => update.mutate({ id: u.id, body: { is_active: false } })}>Deactivate</MenuItem>
                    : <MenuItem icon={<UserCheck className="size-4" />} onSelect={() => update.mutate({ id: u.id, body: { is_active: true } })}>Reactivate</MenuItem>}
                </MenuContent>
              </MenuRoot>) },
          ]} />
        {list.data && <Pagination page={page} size={list.data.size} total={list.data.total} onPage={setPage} />}
      </Card>

      <Modal open={open} onOpenChange={setOpen} title="Add user" description={WHO_IS_NOTIFIED[me?.role ?? "STUDENT"]}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button loading={create.isPending} disabled={!form.full_name || !form.email} onClick={() => create.mutate()}>Create user</Button></>}>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Full name" required className="col-span-2"><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
          <Field label="Email" required className="col-span-2"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@nfsu.ac.in" /></Field>
          <Field label="Role" required className="col-span-2">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {creatable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
          </Field>
          {form.role === "FACULTY" && (
            <Field label="Link to faculty profile" className="col-span-2" hint="Lets them see their own timetable and request availability changes.">
              <Select value={form.faculty_id} onChange={(e) => setForm({ ...form, faculty_id: e.target.value })}>
                <option value="">Not linked</option>{faculty.data?.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.code})</option>)}
              </Select>
            </Field>
          )}
          {form.role === "STUDENT" && <>
            <Field label="Enrollment number" className="col-span-2"><Input value={form.enrollment_no} onChange={(e) => setForm({ ...form, enrollment_no: e.target.value })} placeholder="NFSU26MSDF001" /></Field>
            <Field label="Class"><Select value={form.group_id} onChange={(e) => setForm({ ...form, group_id: e.target.value, batch_id: "" })}>
              <option value="">Select…</option>{groups.data?.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}</Select></Field>
            <Field label="Batch"><Select value={form.batch_id} disabled={!grp?.batches.length} onChange={(e) => setForm({ ...form, batch_id: e.target.value })}>
              <option value="">—</option>{grp?.batches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></Field>
          </>}
        </div>
      </Modal>

      <Modal open={!!secret} onOpenChange={(o) => !o && setSecret(null)} size="sm" title="Temporary password"
        description="Shown only once. Share it securely — the user must change it at first sign-in."
        footer={<Button onClick={() => setSecret(null)}>Done</Button>}>
        {secret && (
          <div className="space-y-3">
            <p className="text-sm">{secret.email}</p>
            <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 p-3 font-mono text-sm">
              <span className="flex-1 break-all">{secret.password}</span>
              <button aria-label="Copy password" onClick={() => void navigator.clipboard.writeText(secret.password).then(() => toast.success("Copied"))} className="rounded-md p-1 text-muted hover:text-ink"><Copy className="size-4" /></button>
            </div>
            <p className="flex items-start gap-2 text-xs text-warn"><ShieldAlert className="mt-0.5 size-4 shrink-0" />Never send passwords over public chat. This event is recorded in the audit log.</p>
          </div>
        )}
      </Modal>
    </>
  );
}

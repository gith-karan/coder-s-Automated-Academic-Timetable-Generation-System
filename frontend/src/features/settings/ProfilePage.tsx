import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { initials, ROLE_LABEL } from "@/lib/utils";
import { useTimeFormat } from "@/app/preferences";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, PageHeader } from "@/components/ui/display";
import { Input } from "@/components/ui/form";
import { PasswordForm } from "@/features/auth/ChangePasswordGate";

export default function ProfilePage() {
  const { me, setMe } = useAuth();
  const { dt } = useTimeFormat();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(me?.full_name ?? "");
  const save = useMutation({
    mutationFn: () => api.patch<Me>("/auth/me", { full_name: name }),
    onSuccess: (m) => { setMe(m); setEditing(false); toast.success("Profile updated"); },
  });
  if (!me) return null;
  return (
    <>
      <PageHeader title="Profile" description="Manage your account information" />
      <div className="grid gap-5 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <div className="mb-6 flex items-center gap-4">
            <div className="grid size-16 place-items-center rounded-full bg-brand text-xl font-bold text-white">{initials(me.full_name)}</div>
            <div className="flex-1">
              <p className="text-lg font-semibold">{me.full_name}</p>
              <p className="text-sm text-muted">{ROLE_LABEL[me.role]}</p>
            </div>
            {!editing && <Button size="sm" icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>Edit profile</Button>}
          </div>
          <dl className="divide-y divide-line text-sm">
            <div className="grid grid-cols-3 py-3"><dt className="text-muted">Name</dt><dd className="col-span-2">
              {editing ? <div className="flex gap-2"><Input value={name} onChange={(e) => setName(e.target.value)} />
                <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
                <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button></div> : me.full_name}
            </dd></div>
            <div className="grid grid-cols-3 py-3"><dt className="text-muted">Email</dt><dd className="col-span-2">{me.email}</dd></div>
            <div className="grid grid-cols-3 py-3"><dt className="text-muted">Role</dt><dd className="col-span-2">{ROLE_LABEL[me.role]}</dd></div>
            {me.enrollment_no && <div className="grid grid-cols-3 py-3"><dt className="text-muted">Enrollment no.</dt><dd className="col-span-2">{me.enrollment_no}</dd></div>}
            <div className="grid grid-cols-3 py-3"><dt className="text-muted">Last sign-in</dt><dd className="col-span-2">{dt(me.last_login_at)}</dd></div>
            <div className="grid grid-cols-3 py-3"><dt className="text-muted">Member since</dt><dd className="col-span-2">{dt(me.created_at)}</dd></div>
          </dl>
        </Card>
        <Card className="lg:col-span-2" title="Change password"><PasswordForm onDone={() => toast.success("Password changed. Other sessions were signed out.")} /></Card>
      </div>
    </>
  );
}

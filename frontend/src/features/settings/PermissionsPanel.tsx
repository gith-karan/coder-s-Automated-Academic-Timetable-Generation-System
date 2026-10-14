import { Fragment, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Save, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { PermissionsView, Role } from "@/lib/types";
import { cn, ROLE_LABEL } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/display";
import { Switch } from "@/components/ui/form";
import { HelpTip, Tip } from "@/components/ui/overlay";

const ROLES: Role[] = ["COORDINATOR", "FACULTY", "STUDENT"];
const RANK: Record<Role, number> = { ADMIN: 40, COORDINATOR: 30, FACULTY: 20, STUDENT: 10 };

/** Role × permission matrix. You can change roles below yours, and only permissions you hold yourself. */
export function PermissionsPanel() {
  const qc = useQueryClient();
  const { me, refresh } = useAuth();
  const { data } = useQuery({ queryKey: ["permissions"], queryFn: () => api.get<PermissionsView>("/permissions") });
  const [draft, setDraft] = useState<PermissionsView["matrix"] | null>(null);
  useEffect(() => { if (data) setDraft(structuredClone(data.matrix)); }, [data]);

  const save = useMutation({
    mutationFn: async () => {
      for (const role of data!.editable_roles as ("COORDINATOR" | "FACULTY" | "STUDENT")[]) {
        if (JSON.stringify([...draft![role]].sort()) !== JSON.stringify([...data!.matrix[role]].sort()))
          await api.put(`/permissions/${role}`, { permissions: draft![role] });
      }
    },
    onSuccess: () => { toast.success("Permissions saved — they apply at each user's next page load"); void qc.invalidateQueries({ queryKey: ["permissions"] }); void refresh(); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save permissions"),
    meta: { silent: true },
  });

  const groups = useMemo(() => {
    const m = new Map<string, PermissionsView["catalogue"]>();
    data?.catalogue.forEach((p) => m.set(p.group, [...(m.get(p.group) ?? []), p]));
    return [...m];
  }, [data]);

  if (!data || !draft) return <Skeleton className="h-96" />;
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.matrix);
  const editable = new Set(data.editable_roles);
  const mine = new Set(data.my_permissions);

  return (
    <Card title={<span className="inline-flex items-center gap-1.5">Roles & permissions <HelpTip>Hierarchy: Admin › Coordinator › Faculty › Student. You can change roles below yours, and only switch permissions you hold yourself. Giving a role “Manage permissions of lower roles” lets it manage the roles below it in the same way. A lock means a role can never hold that permission. The Admin always has everything.</HelpTip></span>} description="What each role may see and do. Changes are audited and higher roles are notified."
      action={<div className="flex gap-2">
        <Button size="sm" variant="secondary" icon={<Undo2 className="size-4" />} disabled={!dirty} onClick={() => setDraft(structuredClone(data.matrix))}>Reset</Button>
        <Button size="sm" icon={<Save className="size-4" />} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>Save permissions</Button>
      </div>}>
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-2 pr-4 font-medium">Permission</th>
              {ROLES.map((r) => (
                <th key={r} className="w-28 py-2 text-center font-medium">
                  {ROLE_LABEL[r]}{!editable.has(r) && <span className="block text-[10px] font-normal">(view only)</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map(([group, perms]) => (
              <Fragment key={group}>
                <tr><td colSpan={4} className="pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-muted">{group}</td></tr>
                {perms.map((p) => (
                  <tr key={p.key} className="border-b border-line/60">
                    <td className="py-2.5 pr-4"><span className="block font-medium">{p.label}</span><span className="text-xs text-muted">{p.description}</span></td>
                    {ROLES.map((r) => {
                      const allowed = RANK[r] >= RANK[p.ceiling];
                      if (!allowed) return <td key={r} className="text-center"><Tip label={`${ROLE_LABEL[r]} can never hold this`}><Lock className="mx-auto size-3.5 text-muted/60" /></Tip></td>;
                      const on = draft[r as "COORDINATOR"].includes(p.key);
                      const can = editable.has(r) && (mine.has(p.key) || me?.role === "ADMIN");
                      return (
                        <td key={r} className={cn("text-center", !can && "opacity-50")}>
                          <div className="inline-flex"><Switch checked={on} disabled={!can}
                            onCheckedChange={(v) => setDraft({ ...draft, [r]: v ? [...draft[r as "COORDINATOR"], p.key] : draft[r as "COORDINATOR"].filter((k) => k !== p.key) })} /></div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

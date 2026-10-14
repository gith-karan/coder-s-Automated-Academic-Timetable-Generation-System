import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Laptop, Moon, Sun } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { ColorTheme } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAuth } from "@/app/auth";
import { usePrefs } from "@/app/preferences";
import { Card, PageHeader, Tabs } from "@/components/ui/display";
import { Field, Input, Segmented, Switch } from "@/components/ui/form";
import { PasswordForm } from "@/features/auth/ChangePasswordGate";
import { useSearchParams } from "react-router-dom";
import { PermissionsPanel } from "./PermissionsPanel";

export const THEMES: { value: ColorTheme; label: string; color: string }[] = [
  { value: "nfsu", label: "NFSU", color: "#a8202c" },
  { value: "blue", label: "Blue", color: "#2563eb" },
  { value: "green", label: "Green", color: "#15803d" },
  { value: "purple", label: "Purple", color: "#7c3aed" },
  { value: "orange", label: "Orange", color: "#ea580c" },
  { value: "teal", label: "Teal", color: "#0d9488" },
];

function Preview() {
  return (
    <div className="overflow-hidden rounded-xl border border-line shadow-sm" aria-hidden>
      <div className="flex h-44">
        <div className="w-16 space-y-2 bg-side p-2">
          <img src="/brand/nfsu-shield.png" alt="" className="mx-auto size-7 object-contain" />
          <div className="h-2 rounded bg-brand" />
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-2 rounded bg-white/15" />)}
        </div>
        <div className="flex-1 space-y-2 bg-bg p-3">
          <div className="h-3 w-24 rounded bg-ink/70" />
          <div className="grid grid-cols-3 gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-10 rounded-lg border border-line bg-surface" />)}</div>
          <div className="grid grid-cols-5 gap-1">{Array.from({ length: 10 }).map((_, i) => <div key={i} className={cn("h-5 rounded", i % 3 === 0 ? "bg-brand/30" : "bg-surface")} />)}</div>
          <div className="h-6 w-20 rounded-md bg-brand" />
        </div>
      </div>
    </div>
  );
}

function SystemSettings() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["system-settings"], queryFn: () => api.get<{ solver_time_limit_s: number }>("/system-settings") });
  const save = useMutation({
    mutationFn: (b: Record<string, unknown>) => api.put("/system-settings", b),
    onSuccess: () => { toast.success("System settings saved"); void qc.invalidateQueries({ queryKey: ["system-settings"] }); },
  });
  if (!data) return null;
  return (
    <div className="space-y-4">
      <Field label="Solver safety cap (seconds)" hint="10–300 s. Default 60 s." help="The engine stops on its own the moment it has proven that no better timetable exists (about 5–10 s for typical data); more time does not improve the result. The cap only protects the server against extremely large or contradictory inputs. If it is ever reached, the best timetable found so far is kept and the report says it was not proven optimal.">
        <Input type="number" min={10} max={300} className="w-32" defaultValue={data.solver_time_limit_s}
          onBlur={(e) => Number(e.target.value) !== data.solver_time_limit_s && save.mutate({ solver_time_limit_s: Number(e.target.value) })} />
      </Field>
      <p className="text-xs text-muted">Who may publish, and whether faculty availability needs approval, are now set per role under <b>Roles &amp; permissions</b>.</p>
    </div>
  );
}

export default function SettingsPage() {
  const { hasRole, can } = useAuth();
  const { prefs, update } = usePrefs();
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") ?? "appearance");
  const tabs = [
    { value: "appearance", label: "Appearance" },
    { value: "preferences", label: "Preferences" },
    ...(hasRole("ADMIN") || can("permissions.manage") ? [{ value: "permissions", label: "Roles & permissions" }] : []),
    ...(hasRole("ADMIN") ? [{ value: "system", label: "System" }] : []),
    { value: "account", label: "Account" },
  ];
  return (
    <>
      <PageHeader title="Settings" description="Customise your interface. Preferences follow you to every device." />
      <Tabs value={tab} onValueChange={setTab} tabs={tabs} className="mb-5" />
      {tab === "appearance" && (
        <div className="grid gap-5 lg:grid-cols-5">
          <Card className="lg:col-span-3" title="Theme">
            <p className="mb-2 text-xs font-medium text-muted">Mode</p>
            <Segmented value={prefs.theme_mode} onChange={(v) => update({ theme_mode: v })}
              options={[{ value: "light", label: "Light", icon: <Sun className="size-4" /> }, { value: "dark", label: "Dark", icon: <Moon className="size-4" /> },
                { value: "system", label: "System", icon: <Laptop className="size-4" /> }]} />
            <p className="mb-2 mt-6 text-xs font-medium text-muted">Colour theme</p>
            <div className="flex flex-wrap gap-4" role="radiogroup" aria-label="Colour theme">
              {THEMES.map((t) => (
                <button key={t.value} role="radio" aria-checked={prefs.color_theme === t.value} onClick={() => update({ color_theme: t.value })}
                  className="flex flex-col items-center gap-1.5 text-xs">
                  <span className={cn("grid size-11 place-items-center rounded-full ring-offset-2 ring-offset-surface transition", prefs.color_theme === t.value && "ring-2 ring-[var(--text)]")} style={{ background: t.color }}>
                    {prefs.color_theme === t.value && <Check className="size-5 text-white" />}
                  </span>
                  {t.label}{t.value === "nfsu" && <span className="-mt-1 text-[10px] text-muted">(Default)</span>}
                </button>
              ))}
            </div>
          </Card>
          <Card className="lg:col-span-2" title="Preview" description="This is how your interface will look."><Preview /></Card>
        </div>
      )}
      {tab === "preferences" && (
        <Card className="max-w-2xl">
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span><span className="block text-sm font-medium">Time format</span><span className="block text-xs text-muted">How times are shown everywhere in the app.</span></span>
              <Segmented value={prefs.time_format ?? "12h"} onChange={(v) => update({ time_format: v })}
                options={[{ value: "12h", label: "12-hour (2:30 PM)" }, { value: "24h", label: "24-hour (14:30)" }]} />
            </div>
            <Switch checked={prefs.compact_sidebar} onCheckedChange={(v) => update({ compact_sidebar: v })} label="Compact sidebar" description="Show icons only to give the timetable more room." />
            <Switch checked={prefs.show_tooltips} onCheckedChange={(v) => update({ show_tooltips: v })} label="Show tooltips" description="Explain icon buttons on hover." />
            <Switch checked={prefs.animations} onCheckedChange={(v) => update({ animations: v })} label="Animations" description="Subtle transitions. Turn off for reduced motion." />
          </div>
        </Card>
      )}
      {tab === "permissions" && <PermissionsPanel />}
      {tab === "system" && <Card className="max-w-2xl" title="Generation safety" description="Only admins can change this. Every change is audited."><SystemSettings /></Card>}
      {tab === "account" && <Card className="max-w-md" title="Change password"><PasswordForm onDone={() => toast.success("Password changed. Other sessions were signed out.")} /></Card>}
    </>
  );
}

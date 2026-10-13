import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/form";

export type Values = Record<string, unknown>;

export interface FieldDef {
  name: string;
  label: string;
  type?: "text" | "number" | "email" | "select" | "multiselect" | "switch" | "textarea";
  options?: { value: string; label: string }[];
  required?: boolean;
  placeholder?: string;
  hint?: ReactNode;
  min?: number;
  max?: number;
  half?: boolean;
  show?: (v: Values) => boolean;
  validate?: (value: unknown, all: Values) => string | undefined;
}

/** Config-driven form used by every resource drawer: same look, validation and error handling everywhere. */
export function EntityForm({ id, fields, initial, onSubmit, serverErrors }: {
  id: string;
  fields: FieldDef[];
  initial: Values;
  onSubmit: (v: Values) => void;
  serverErrors?: Record<string, string>;
}) {
  const [values, setValues] = useState<Values>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => setValues(initial), [initial]);
  useEffect(() => setErrors(serverErrors ?? {}), [serverErrors]);

  const set = (name: string, v: unknown) => {
    setValues((s) => ({ ...s, [name]: v }));
    setErrors((e) => ({ ...e, [name]: "" }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    for (const f of fields) {
      if (f.show && !f.show(values)) continue;
      const v = values[f.name];
      if (f.required && (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length))) errs[f.name] = `${f.label} is required`;
      else if (f.type === "number" && v !== "" && v != null) {
        const n = Number(v);
        if (Number.isNaN(n)) errs[f.name] = "Enter a number";
        else if (f.min !== undefined && n < f.min) errs[f.name] = `Must be at least ${f.min}`;
        else if (f.max !== undefined && n > f.max) errs[f.name] = `Must be at most ${f.max}`;
      }
      const custom = f.validate?.(v, values);
      if (custom) errs[f.name] = custom;
    }
    setErrors(errs);
    if (Object.values(errs).some(Boolean)) return;
    const out: Values = {};
    for (const f of fields) {
      if (f.show && !f.show(values)) continue;
      const v = values[f.name];
      out[f.name] = f.type === "number" ? (v === "" || v == null ? null : Number(v)) : v === "" && !f.required ? null : v;
    }
    onSubmit(out);
  };

  return (
    <form id={id} onSubmit={submit} className="grid grid-cols-2 gap-4" noValidate>
      {fields.map((f) => {
        if (f.show && !f.show(values)) return null;
        const v = values[f.name];
        const err = errors[f.name];
        const fid = `${id}-${f.name}`;
        return (
          <Field key={f.name} label={f.type === "switch" ? undefined : f.label} htmlFor={fid} error={err} hint={f.hint}
            required={f.required} className={cn(f.half ? "col-span-2 sm:col-span-1" : "col-span-2")}>
            {f.type === "select" ? (
              <Select id={fid} value={String(v ?? "")} invalid={!!err} onChange={(e) => set(f.name, e.target.value)}>
                <option value="">{f.placeholder ?? "Select…"}</option>
                {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            ) : f.type === "multiselect" ? (
              <div className="flex flex-wrap gap-1.5 rounded-[10px] border border-line p-2">
                {f.options?.map((o) => {
                  const arr = (v as string[]) ?? [];
                  const on = arr.includes(o.value);
                  return (
                    <button key={o.value} type="button" aria-pressed={on}
                      onClick={() => set(f.name, on ? arr.filter((x) => x !== o.value) : [...arr, o.value])}
                      className={cn("rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                        on ? "border-brand bg-brand/10 text-brand" : "border-line text-muted hover:text-ink")}>
                      {o.label}
                    </button>
                  );
                })}
                {!f.options?.length && <span className="text-xs text-muted">No options available</span>}
              </div>
            ) : f.type === "switch" ? (
              <Switch checked={Boolean(v)} onCheckedChange={(c) => set(f.name, c)} label={f.label} />
            ) : f.type === "textarea" ? (
              <Textarea id={fid} value={String(v ?? "")} onChange={(e) => set(f.name, e.target.value)} placeholder={f.placeholder} />
            ) : (
              <Input id={fid} type={f.type ?? "text"} value={v == null ? "" : String(v)} invalid={!!err} min={f.min} max={f.max}
                placeholder={f.placeholder} onChange={(e) => set(f.name, e.target.value)} />
            )}
          </Field>
        );
      })}
    </form>
  );
}

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useDebounced, useList, useRemove, useSave } from "@/lib/hooks";
import { Button, IconButton } from "@/components/ui/button";
import { Card, EmptyState, PageHeader } from "@/components/ui/display";
import { Input } from "@/components/ui/form";
import { Drawer, Modal } from "@/components/ui/overlay";
import { DataTable, Pagination, type Column } from "@/components/ui/table";
import { EntityForm, type FieldDef, type Values } from "./EntityForm";

export interface ResourceConfig<T extends { id: string }> {
  resource: string;
  title: string;
  description: string;
  singular: string;
  icon: ReactNode;
  columns: Column<T>[];
  fields: FieldDef[];
  emptyValues: Values;
  toValues: (row: T) => Values;
  toBody?: (v: Values, row?: T) => unknown;
  label: (row: T) => string;
  filters?: (set: (k: string, v: string) => void, f: Record<string, string>) => ReactNode;
  extraTabs?: (row: T, close: () => void) => ReactNode; // rendered below the form when editing
  drawerWidth?: string;
}

/** One page implementation for every master-data list (programmes, subjects, faculty, rooms…). */
export function ResourcePage<T extends { id: string }>({ cfg }: { cfg: ResourceConfig<T> }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<T | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<T | null>(null);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const dq = useDebounced(q);
  const list = useList<T>(cfg.resource, { q: dq, page, size: 10, ...filters });
  const save = useSave<T>(cfg.resource);
  const remove = useRemove(cfg.resource);
  const [params, setParams] = useSearchParams();

  // Deep link from "Fix →" in diagnostics: /faculty?open=<id> opens that record straight away.
  useEffect(() => {
    const id = params.get("open");
    if (!id) return;
    api.get<T>(`/${cfg.resource}/${id}`).then(setEditing).catch(() => toast.error(`${cfg.singular} not found`));
    setParams((p) => { p.delete("open"); return p; }, { replace: true });
  }, [params, cfg.resource, cfg.singular, setParams]);

  const close = () => { setEditing(null); setCreating(false); setServerErrors({}); };
  const onSubmit = (v: Values) => {
    const body = cfg.toBody ? cfg.toBody(v, editing ?? undefined) : v;
    save.mutate({ id: editing?.id, body }, {
      onSuccess: () => { toast.success(`${cfg.singular} ${editing ? "updated" : "created"}`); close(); },
      onError: (e) => {
        if (e instanceof ApiError && e.errors.length) {
          setServerErrors(Object.fromEntries(e.errors.map((x) => [x.field.split(".")[0], x.message])));
        }
        toast.error(e instanceof ApiError ? e.message : "Could not save");
      },
    });
  };

  const columns: Column<T>[] = [
    ...cfg.columns,
    {
      key: "_actions", header: <span className="sr-only">Actions</span>, className: "w-24 text-right",
      cell: (r) => (
        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          <IconButton label={`Edit ${cfg.label(r)}`} size="sm" onClick={() => setEditing(r)}><Pencil className="size-4" /></IconButton>
          <IconButton label={`Delete ${cfg.label(r)}`} size="sm" className="hover:text-bad" onClick={() => setDeleting(r)}><Trash2 className="size-4" /></IconButton>
        </div>
      ),
    },
  ];

  const formOpen = creating || !!editing;
  // Stable initial values: the form resets only when a different row is opened.
  const initial = useMemo(() => (editing ? cfg.toValues(editing) : cfg.emptyValues), [editing, creating]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <PageHeader title={cfg.title} description={cfg.description}
        actions={<Button icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>Add {cfg.singular.toLowerCase()}</Button>} />
      <Card className="overflow-hidden [&>div]:p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-4">
          <div className="w-full max-w-xs">
            <Input icon={<Search />} placeholder={`Search ${cfg.title.toLowerCase()}…`} value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label={`Search ${cfg.title}`} />
          </div>
          {cfg.filters?.((k, v) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); }, filters)}
        </div>
        <DataTable columns={columns} rows={list.data?.items} loading={list.isLoading} onRowClick={(r) => setEditing(r)}
          empty={<EmptyState icon={cfg.icon} title={q ? "No matches" : `No ${cfg.title.toLowerCase()} yet`}
            description={q ? "Try a different search." : `Add your first ${cfg.singular.toLowerCase()} to get started.`}
            action={!q && <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>Add {cfg.singular.toLowerCase()}</Button>} />} />
        {list.data && <Pagination page={page} size={list.data.size} total={list.data.total} onPage={setPage} />}
      </Card>

      <Drawer open={formOpen} onOpenChange={(o) => !o && close()} width={cfg.drawerWidth}
        title={editing ? `Edit ${cfg.label(editing)}` : `New ${cfg.singular.toLowerCase()}`}
        footer={<>
          <Button variant="secondary" onClick={close}>Cancel</Button>
          <Button type="submit" form="entity-form" loading={save.isPending}>Save</Button>
        </>}>
        {formOpen && (
          <>
            <EntityForm id="entity-form" fields={cfg.fields} initial={initial}
              onSubmit={onSubmit} serverErrors={serverErrors} />
            {editing && cfg.extraTabs?.(editing, close)}
          </>
        )}
      </Drawer>

      <Modal open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} size="sm" title={`Delete ${deleting ? cfg.label(deleting) : ""}?`}
        description="This cannot be undone. The deletion is recorded in the audit log."
        footer={<>
          <Button variant="secondary" onClick={() => setDeleting(null)}>Cancel</Button>
          <Button variant="danger" loading={remove.isPending}
            onClick={() => deleting && remove.mutate(deleting.id, { onSuccess: () => { toast.success(`${cfg.singular} deleted`); setDeleting(null); } })}>
            Delete
          </Button>
        </>}>
        <p className="text-sm text-muted">Items that are still used elsewhere (for example a room used by a timetable) cannot be deleted.</p>
      </Modal>
    </>
  );
}

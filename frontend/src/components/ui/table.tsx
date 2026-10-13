import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "./display";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  className?: string;
  hideOnMobile?: boolean;
}

/** One table component for every list page. */
export function DataTable<T extends object>({
  columns, rows, loading, empty, onRowClick, rowKey,
}: {
  columns: Column<T>[]; rows: T[] | undefined; loading?: boolean; empty?: ReactNode;
  onRowClick?: (row: T) => void; rowKey?: (row: T) => string;
}) {
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs font-medium text-muted">
            {columns.map((c) => (
              <th key={c.key} className={cn("px-4 py-3 font-medium whitespace-nowrap", c.hideOnMobile && "hidden md:table-cell", c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b border-line/60">
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-4 py-3", c.hideOnMobile && "hidden md:table-cell")}>
                    <Skeleton className="h-4 w-full max-w-40" />
                  </td>
                ))}
              </tr>
            ))}
          {!loading &&
            rows?.map((r, i) => (
              <tr
                key={rowKey ? rowKey(r) : ((r as { id?: string }).id ?? i)}
                onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={cn("border-b border-line/60 transition-colors last:border-0", onRowClick && "cursor-pointer hover:bg-surface-2")}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-4 py-3 align-middle", c.hideOnMobile && "hidden md:table-cell", c.className)}>
                    {c.cell(r)}
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
      {!loading && rows?.length === 0 && empty}
    </div>
  );
}

export function Pagination({ page, size, total, onPage }: { page: number; size: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (total <= size) return <p className="px-4 py-3 text-xs text-muted">{total} item{total === 1 ? "" : "s"}</p>;
  const nums = Array.from({ length: pages }, (_, i) => i + 1).filter((n) => n === 1 || n === pages || Math.abs(n - page) <= 1);
  return (
    <div className="flex items-center justify-between gap-2 px-4 py-3">
      <p className="text-xs text-muted">
        {(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}
      </p>
      <div className="flex items-center gap-1">
        <button aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-line/60 disabled:opacity-30">
          <ChevronLeft className="size-4" />
        </button>
        {nums.map((n, i) => (
          <span key={n} className="flex items-center">
            {i > 0 && nums[i - 1] !== n - 1 && <span className="px-1 text-muted">…</span>}
            <button
              onClick={() => onPage(n)}
              aria-current={n === page ? "page" : undefined}
              className={cn("grid size-8 place-items-center rounded-lg text-xs font-medium", n === page ? "bg-brand text-brand-fg" : "text-muted hover:bg-line/60")}
            >
              {n}
            </button>
          </span>
        ))}
        <button aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)} className="grid size-8 place-items-center rounded-lg text-muted hover:bg-line/60 disabled:opacity-30">
          <ChevronRight className="size-4" />
        </button>
      </div>
    </div>
  );
}

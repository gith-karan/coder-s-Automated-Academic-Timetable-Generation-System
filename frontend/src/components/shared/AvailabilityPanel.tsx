import { useEffect, useState, type ReactNode } from "react";
import { Pencil, Save, X } from "lucide-react";
import type { Grid } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { SlotPainter, type SlotState } from "./SlotPainter";

type Slots = Map<`${number}:${number}`, SlotState>;

/** Weekly grid that opens in VIEW mode; "Edit" switches on the brushes, then Save or Cancel. */
export function AvailabilityPanel({ grid, initial, brushes, canEdit, onSave, saveLabel = "Save availability", extra }: {
  grid: Grid;
  initial: Slots;
  brushes?: ("available" | "preferred" | "unavailable")[];
  canEdit: boolean;
  onSave: (slots: Slots) => Promise<boolean>;
  saveLabel?: string;
  extra?: ReactNode; // e.g. a "reason" box shown only while editing
}) {
  const [editing, setEditing] = useState(false);
  const [slots, setSlots] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => setSlots(initial), [initial]);
  const dirty = [...slots].some(([k, v]) => initial.get(k) !== v);

  const save = async () => {
    setBusy(true);
    const ok = await onSave(slots);
    setBusy(false);
    if (ok) setEditing(false);
  };

  return (
    <div className="space-y-3">
      <SlotPainter grid={grid} value={slots} onChange={setSlots} brushes={brushes} readOnly={!editing} />
      {editing && extra}
      {canEdit && (
        <div className="flex justify-end gap-2">
          {!editing ? (
            <Button variant="outline" icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>Edit availability</Button>
          ) : (
            <>
              <Button variant="secondary" icon={<X className="size-4" />} onClick={() => { setSlots(initial); setEditing(false); }}>Cancel</Button>
              <Button icon={<Save className="size-4" />} loading={busy} disabled={!dirty} onClick={save}>{saveLabel}</Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

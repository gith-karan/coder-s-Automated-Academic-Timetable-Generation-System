import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Send } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { CalendarData, Faculty } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { Textarea } from "@/components/ui/form";
import { availabilityToSlots, SlotPainter, slotsToAvailability } from "@/components/shared/SlotPainter";

/** Faculty availability painter. Staff changes apply immediately; faculty changes become an approval request. */
export function AvailabilityEditor({ faculty, asRequest }: { faculty: Faculty; asRequest?: boolean }) {
  const qc = useQueryClient();
  const cal = useQuery({ queryKey: ["calendar"], queryFn: () => api.get<CalendarData>("/calendar") });
  const initial = useMemo(() => (cal.data ? availabilityToSlots(cal.data.grid, faculty.availability ?? {}) : null), [cal.data, faculty]);
  const [slots, setSlots] = useState(initial);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setSlots(initial), [initial]);

  if (!cal.data || !slots) return <Skeleton className="h-64" />;

  const save = async () => {
    setBusy(true);
    try {
      const availability = slotsToAvailability(cal.data.grid, slots, faculty.availability ?? {});
      const r = await api.put<{ applied: boolean }>(`/faculty/${faculty.id}/availability`, { availability, reason });
      toast.success(r.applied ? "Availability updated" : "Sent to the coordinator for approval");
      void qc.invalidateQueries({ queryKey: ["faculty"] });
      void qc.invalidateQueries({ queryKey: ["requests"] });
      setReason("");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save availability");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <SlotPainter grid={cal.data.grid} value={slots} onChange={setSlots} />
      {asRequest && (
        <Textarea placeholder="Reason for the change (shown to the coordinator)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
      )}
      <div className="flex justify-end">
        <Button onClick={save} loading={busy} icon={asRequest ? <Send className="size-4" /> : <CalendarDays className="size-4" />}>
          {asRequest ? "Send for approval" : "Save availability"}
        </Button>
      </div>
    </div>
  );
}

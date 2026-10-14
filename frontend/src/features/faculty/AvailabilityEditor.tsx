import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { CalendarData, Faculty } from "@/lib/types";
import { Skeleton } from "@/components/ui/display";
import { Textarea } from "@/components/ui/form";
import { AvailabilityPanel } from "@/components/shared/AvailabilityPanel";
import { availabilityToSlots, slotsToAvailability } from "@/components/shared/SlotPainter";

/** Faculty availability. Direct save for people allowed to change it; otherwise it becomes an approval request. */
export function AvailabilityEditor({ faculty, asRequest, canEdit = true }: { faculty: Faculty; asRequest?: boolean; canEdit?: boolean }) {
  const qc = useQueryClient();
  const cal = useQuery({ queryKey: ["calendar"], queryFn: () => api.get<CalendarData>("/calendar") });
  const initial = useMemo(() => (cal.data ? availabilityToSlots(cal.data.grid, faculty.availability ?? {}) : null), [cal.data, faculty]);
  const [reason, setReason] = useState("");
  if (!cal.data || !initial) return <Skeleton className="h-64" />;

  const save = async (slots: typeof initial) => {
    try {
      const availability = slotsToAvailability(cal.data.grid, slots, faculty.availability ?? {});
      const r = await api.put<{ applied: boolean }>(`/faculty/${faculty.id}/availability`, { availability, reason });
      toast.success(r.applied ? "Availability updated" : "Sent to the coordinator for approval");
      void qc.invalidateQueries({ queryKey: ["faculty"] });
      void qc.invalidateQueries({ queryKey: ["requests"] });
      setReason("");
      return true;
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save availability");
      return false;
    }
  };

  return (
    <AvailabilityPanel grid={cal.data.grid} initial={initial} canEdit={canEdit} onSave={save}
      saveLabel={asRequest ? "Send for approval" : "Save availability"}
      extra={asRequest && <Textarea placeholder="Reason for the change (shown to the coordinator)" value={reason}
        onChange={(e) => setReason(e.target.value)} maxLength={500} />} />
  );
}

import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import { api } from "@/lib/api";
import type { Faculty } from "@/lib/types";
import { useAuth } from "@/app/auth";
import { HelpTip } from "@/components/ui/overlay";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/display";
import { AvailabilityEditor } from "./AvailabilityEditor";

export default function MyAvailabilityPage() {
  const { me, can } = useAuth();
  const direct = can("availability.edit_own");
  const fac = useQuery({
    queryKey: ["faculty", me?.faculty_id],
    queryFn: () => api.get<Faculty>("/me/faculty-profile"),
    enabled: !!me?.faculty_id,
  });
  return (
    <>
      <PageHeader title={<span className="inline-flex items-center gap-1.5">My Availability <HelpTip>Click Edit availability, paint red where you cannot teach and gold where you prefer to teach, then save. If approval is required, the coordinator is notified and you get a notification with the decision.</HelpTip></span>} description={direct ? "Tell the generator when you can teach. Your changes apply immediately." : "Tell the timetable coordinator when you can teach. Changes are reviewed before they take effect."} />
      {!me?.faculty_id ? (
        <Card><EmptyState icon={<CalendarDays />} title="No faculty profile linked" description="Ask the coordinator to link your account to your faculty profile." /></Card>
      ) : !fac.data ? <Skeleton className="h-96" /> : (
        <Card>
          <AvailabilityEditor faculty={fac.data} asRequest={!direct} />
        </Card>
      )}
    </>
  );
}

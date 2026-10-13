import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Info } from "lucide-react";
import { api } from "@/lib/api";
import type { Faculty } from "@/lib/types";
import { useAuth } from "@/app/auth";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/display";
import { AvailabilityEditor } from "./AvailabilityEditor";

export default function MyAvailabilityPage() {
  const { me } = useAuth();
  const fac = useQuery({
    queryKey: ["faculty", me?.faculty_id],
    queryFn: () => api.get<Faculty>(`/faculty/${me!.faculty_id}`),
    enabled: !!me?.faculty_id,
  });
  return (
    <>
      <PageHeader title="My Availability" description="Tell the timetable coordinator when you can teach. Changes are reviewed before they take effect." />
      {!me?.faculty_id ? (
        <Card><EmptyState icon={<CalendarDays />} title="No faculty profile linked" description="Ask the coordinator to link your account to your faculty profile." /></Card>
      ) : !fac.data ? <Skeleton className="h-96" /> : (
        <Card>
          <p className="mb-4 flex items-start gap-2 rounded-xl bg-info/8 p-3 text-xs text-info">
            <Info className="mt-0.5 size-4 shrink-0" /> Paint red where you cannot teach and gold where you prefer to teach, then send it for approval.
            You'll get a notification when the coordinator responds.
          </p>
          <AvailabilityEditor faculty={fac.data} asRequest />
        </Card>
      )}
    </>
  );
}

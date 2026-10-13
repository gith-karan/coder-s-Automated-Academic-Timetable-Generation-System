import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, useLocation } from "react-router-dom";
import { Spinner } from "@/components/ui/display";
import type { Role } from "@/lib/types";
import { useAuth } from "./auth";
import { AppLayout } from "./Layout";
import { NAV } from "./nav";

const LoginPage = lazy(() => import("@/features/auth/LoginPage"));
const ChangePasswordGate = lazy(() => import("@/features/auth/ChangePasswordGate"));
const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const CalendarPage = lazy(() => import("@/features/calendar/CalendarPage"));
const ProgrammesPage = lazy(() => import("@/features/programmes/ProgrammesPage"));
const SubjectsPage = lazy(() => import("@/features/subjects/SubjectsPage"));
const FacultyPage = lazy(() => import("@/features/faculty/FacultyPage"));
const MyAvailabilityPage = lazy(() => import("@/features/faculty/MyAvailabilityPage"));
const RoomsPage = lazy(() => import("@/features/rooms/RoomsPage"));
const ConstraintsPage = lazy(() => import("@/features/constraints/ConstraintsPage"));
const GeneratePage = lazy(() => import("@/features/generate/GeneratePage"));
const ReportPage = lazy(() => import("@/features/generate/ReportPage"));
const TimetablePage = lazy(() => import("@/features/timetable/TimetablePage"));
const ReportsPage = lazy(() => import("@/features/reports/ReportsPage"));
const RequestsPage = lazy(() => import("@/features/requests/RequestsPage"));
const UsersPage = lazy(() => import("@/features/users/UsersPage"));
const AuditPage = lazy(() => import("@/features/audit/AuditPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const ProfilePage = lazy(() => import("@/features/settings/ProfilePage"));

function FullScreenLoader() {
  return (
    <div className="grid h-full place-items-center">
      <Spinner className="size-6" />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <FullScreenLoader />;
  if (!me) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (me.must_change_password) return <ChangePasswordGate />;
  return <>{children}</>;
}

/** Route-level RBAC mirrors the navigation config (the server enforces it independently). */
function Guard({ path, roles, children }: { path?: string; roles?: Role[]; children: ReactNode }) {
  const { me } = useAuth();
  const allowed = roles ?? NAV.find((n) => n.to === path)?.roles;
  if (allowed && me && !allowed.includes(me.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

const page = (el: ReactNode, path?: string, roles?: Role[]) => (
  <Guard path={path} roles={roles}>
    <Suspense fallback={<FullScreenLoader />}>{el}</Suspense>
  </Guard>
);

export const router = createBrowserRouter([
  { path: "/login", element: <Suspense fallback={<FullScreenLoader />}><LoginPage /></Suspense> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: page(<DashboardPage />) },
      { path: "calendar", element: page(<CalendarPage />, "/calendar") },
      { path: "programmes", element: page(<ProgrammesPage />, "/programmes") },
      { path: "subjects", element: page(<SubjectsPage />, "/subjects") },
      { path: "faculty", element: page(<FacultyPage />, "/faculty") },
      { path: "availability", element: page(<MyAvailabilityPage />, "/availability") },
      { path: "rooms", element: page(<RoomsPage />, "/rooms") },
      { path: "constraints", element: page(<ConstraintsPage />, "/constraints") },
      { path: "generate", element: page(<GeneratePage />, "/generate") },
      { path: "generate/report/:runId", element: page(<ReportPage />, "/generate") },
      { path: "timetable", element: page(<TimetablePage />, "/timetable") },
      { path: "reports", element: page(<ReportsPage />, "/reports") },
      { path: "requests", element: page(<RequestsPage />, "/requests") },
      { path: "users", element: page(<UsersPage />, "/users") },
      { path: "audit", element: page(<AuditPage />, "/audit") },
      { path: "settings", element: page(<SettingsPage />, "/settings") },
      { path: "profile", element: page(<ProfilePage />) },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

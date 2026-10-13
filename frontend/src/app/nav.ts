import {
  BarChart3, Building2, CalendarClock, CalendarRange, ClipboardCheck, GraduationCap, LayoutDashboard, ScrollText,
  Settings, SlidersHorizontal, Sparkles, UserCog, Users, BookOpen, CalendarDays, type LucideIcon,
} from "lucide-react";
import type { Role } from "@/lib/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  roles: Role[];
  section: "main" | "setup" | "schedule" | "admin";
}

const STAFF: Role[] = ["ADMIN", "COORDINATOR"];
const ALL: Role[] = ["ADMIN", "COORDINATOR", "FACULTY", "STUDENT"];

/** Single source of truth for navigation + route access. Pages/buttons a role cannot use are never shown. */
export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, roles: ALL, section: "main" },
  { to: "/calendar", label: "Academic Calendar", icon: CalendarClock, roles: STAFF, section: "setup" },
  { to: "/programmes", label: "Programmes", icon: GraduationCap, roles: STAFF, section: "setup" },
  { to: "/subjects", label: "Subjects", icon: BookOpen, roles: STAFF, section: "setup" },
  { to: "/faculty", label: "Faculty", icon: Users, roles: STAFF, section: "setup" },
  { to: "/rooms", label: "Classrooms & Labs", icon: Building2, roles: STAFF, section: "setup" },
  { to: "/constraints", label: "Constraints", icon: SlidersHorizontal, roles: STAFF, section: "setup" },
  { to: "/generate", label: "Generate Timetable", icon: Sparkles, roles: STAFF, section: "schedule" },
  { to: "/timetable", label: "Timetable", icon: CalendarRange, roles: ALL, section: "schedule" },
  { to: "/availability", label: "My Availability", icon: CalendarDays, roles: ["FACULTY"], section: "schedule" },
  { to: "/reports", label: "Reports", icon: BarChart3, roles: STAFF, section: "schedule" },
  { to: "/requests", label: "Approvals", icon: ClipboardCheck, roles: ["ADMIN", "COORDINATOR", "FACULTY"], section: "admin" },
  { to: "/users", label: "Users", icon: UserCog, roles: ["ADMIN", "COORDINATOR", "FACULTY"], section: "admin" },
  { to: "/audit", label: "Audit Log", icon: ScrollText, roles: ["ADMIN"], section: "admin" },
  { to: "/settings", label: "Settings", icon: Settings, roles: ALL, section: "admin" },
];

export const SECTION_LABEL = { main: "", setup: "Setup", schedule: "Schedule", admin: "Administration" } as const;

export function navFor(role: Role | undefined) {
  return NAV.filter((n) => role && n.roles.includes(role));
}

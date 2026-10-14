import {
  BarChart3, Building2, CalendarClock, CalendarRange, ClipboardCheck, GraduationCap, LayoutDashboard, ScrollText,
  Settings, SlidersHorizontal, Sparkles, UserCog, Users, BookOpen, CalendarDays, type LucideIcon,
} from "lucide-react";
import type { Me } from "@/lib/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Visible when the user holds ANY of these permissions (empty = everyone). */
  anyOf: string[];
  section: "main" | "setup" | "schedule" | "admin";
  facultyOnly?: boolean;
}

/** Single source of truth for navigation + route access, driven by the admin-configurable permissions. */
export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, anyOf: [], section: "main" },
  { to: "/calendar", label: "Academic Calendar", icon: CalendarClock, anyOf: ["setup.view"], section: "setup" },
  { to: "/programmes", label: "Programmes", icon: GraduationCap, anyOf: ["setup.view"], section: "setup" },
  { to: "/subjects", label: "Subjects", icon: BookOpen, anyOf: ["setup.view"], section: "setup" },
  { to: "/faculty", label: "Faculty", icon: Users, anyOf: ["setup.view"], section: "setup" },
  { to: "/rooms", label: "Classrooms & Labs", icon: Building2, anyOf: ["setup.view"], section: "setup" },
  { to: "/constraints", label: "Constraints & Rules", icon: SlidersHorizontal, anyOf: ["setup.view"], section: "setup" },
  { to: "/generate", label: "Generate Timetable", icon: Sparkles, anyOf: ["timetable.generate"], section: "schedule" },
  { to: "/timetable", label: "Timetable", icon: CalendarRange, anyOf: ["timetable.view_published", "timetable.view_drafts"], section: "schedule" },
  { to: "/availability", label: "My Availability", icon: CalendarDays, anyOf: ["availability.request", "availability.edit_own"], section: "schedule", facultyOnly: true },
  { to: "/reports", label: "Reports", icon: BarChart3, anyOf: ["reports.view"], section: "schedule" },
  { to: "/requests", label: "Approvals", icon: ClipboardCheck, anyOf: ["requests.review", "timetable.publish", "timetable.submit", "availability.request", "session.request_move"], section: "admin" },
  { to: "/users", label: "Users", icon: UserCog, anyOf: ["users.view"], section: "admin" },
  { to: "/audit", label: "Audit Log", icon: ScrollText, anyOf: ["audit.view"], section: "admin" },
  { to: "/settings", label: "Settings", icon: Settings, anyOf: [], section: "admin" },
];

export const SECTION_LABEL = { main: "", setup: "Setup", schedule: "Schedule", admin: "Administration" } as const;

export function allowed(item: NavItem, me: Me | null): boolean {
  if (!me) return false;
  if (item.facultyOnly && !me.faculty_id) return false;
  return item.anyOf.length === 0 || item.anyOf.some((p) => me.permissions.includes(p));
}

export function navFor(me: Me | null) {
  return NAV.filter((n) => allowed(n, me));
}

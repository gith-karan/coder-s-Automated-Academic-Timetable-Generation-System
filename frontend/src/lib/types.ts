export type Role = "ADMIN" | "COORDINATOR" | "FACULTY" | "STUDENT";
export type ThemeMode = "light" | "dark" | "system";
export type ColorTheme = "nfsu" | "blue" | "green" | "purple" | "orange" | "teal";

export interface Preferences {
  theme_mode: ThemeMode;
  color_theme: ColorTheme;
  compact_sidebar: boolean;
  show_tooltips: boolean;
  animations: boolean;
}

export interface Me {
  id: string;
  email: string;
  username: string | null;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  faculty_id: string | null;
  group_id: string | null;
  batch_id: string | null;
  enrollment_no: string | null;
  preferences: Partial<Preferences>;
  permissions: string[];
}

export interface UserRow extends Omit<Me, "permissions"> {
  created_by: { id: string; full_name: string; email: string; role: Role } | null;
}

export interface Paged<T> { items: T[]; total: number; page: number; size: number }

export interface LabType { id: string; name: string; description: string | null }
export interface TimeRange { day: number; start: string; end: string; reason?: string }

export interface Room {
  id: string; code: string; name: string; kind: "CLASSROOM" | "LAB"; lab_type_id: string | null;
  lab_type: LabType | null; capacity: number; building: string | null; is_active: boolean; unavailable: TimeRange[];
}

export interface Programme {
  id: string; code: string; name: string; level: "UG" | "PG" | "INTEGRATED" | "PHD" | "DIPLOMA";
  school: string; duration_semesters: number;
  coordinator_id: string | null; coordinator: { id: string; full_name: string; email: string } | null;
}

export interface Batch { id: string; name: string; strength: number }
export interface Group {
  id: string; programme_id: string; semester: number; section: string; strength: number;
  max_periods_per_day: number | null; home_room_id: string | null; batches: Batch[]; label: string;
}

export interface Availability {
  available?: TimeRange[] | null;
  unavailable?: TimeRange[];
  preferred?: TimeRange[];
  commitments?: TimeRange[];
}

export interface Faculty {
  id: string; code: string; name: string; email: string; designation: string; school: string;
  max_periods_per_day: number | null; max_periods_per_week: number | null; availability: Availability;
}

export interface Subject {
  id: string; code: string; name: string; programme_id: string; semester: number; kind: "THEORY" | "PRACTICAL";
  periods_per_week: number; sessions_per_week: number; consecutive_periods: number; lab_type_id: string | null;
  lab_type: LabType | null; credits: number | null; faculty: { id: string; code: string; name: string }[];
}

export interface GridPeriod { index: number; start: string; end: string }
export interface GridDay { day: number; name: string; short: string; periods: GridPeriod[] }
export interface Grid {
  days: GridDay[]; breaks: { name: string; start: string; end: string; days: number[] | null }[];
  periods_per_week: number; longest_block: number;
}

export interface CalendarData {
  working_days: number[]; day_start: string; day_end: string; period_minutes: number;
  academic_year: string; term_label: string;
  breaks: { name: string; start_time: string; end_time: string; days: number[] | null }[];
  grid: Grid;
}

export type TimetableStatus = "DRAFT" | "IN_REVIEW" | "PUBLISHED" | "ARCHIVED";
export interface TimetableSummary {
  id: string; name: string; status: TimetableStatus; quality_score: number | null; is_complete: boolean;
  row_version: number; programme_ids: string[]; semesters: number[]; total_sessions: number; scheduled: number;
  unassigned: number; locked: number; created_at: string | null; updated_at: string | null;
  submitted_at: string | null; published_at: string | null; review_comment: string | null;
  parent_id: string | null; last_run_id: string | null;
}

export interface Entry {
  id: string; session_key: string; day: number | null; start_period: number | null; length: number; locked: boolean;
  subject: { id: string; code: string; name: string; kind: "THEORY" | "PRACTICAL" };
  group: { id: string; label: string; programme_id: string | null; semester: number | null };
  batch: { id: string; name: string } | null;
  faculty: { id: string; name: string; code: string }[];
  room: { id: string; code: string; name: string } | null;
  color: number;
}

export interface TimetableView { timetable: TimetableSummary; grid: Grid; entries: Entry[]; unassigned: Entry[] }

export interface MoveCell {
  day: number; period: number; status: "ok" | "warning" | "blocked"; reasons: string[];
  best_room_id: string | null; current?: boolean;
}

export interface Diagnostic {
  code: string; severity: "ERROR" | "WARNING"; message: string;
  entities?: { type: string; id: string; label: string }[]; sessions?: string[];
  fix?: { page: string; id?: string; tab?: string } | null;
}

export interface Unassigned {
  key: string; subject_code?: string; subject_name?: string; audience?: string; kind?: string; length?: number;
  faculty?: string[]; candidate_slots?: number; reason?: string;
}

export type RunStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "INFEASIBLE" | "PRECHECK_FAILED" | "TIMEOUT" | "CANCELLED" | "FAILED";
export interface Run {
  id: string; timetable_id: string; status: RunStatus; mode: string; time_limit_s: number;
  stats: {
    scheduled?: number; total?: number; wall_time_s?: number; optimal?: boolean; solver_status?: string;
    quality?: { quality: number; completeness: number; breakdown: Record<string, { label: string; score: number; weight: number }> } | null;
    variables?: number; locked?: number; periods_per_week?: number;
  };
  diagnostics: Diagnostic[]; unassigned: Unassigned[]; created_at: string; started_at: string | null; finished_at: string | null;
}

export interface Readiness {
  ready: boolean;
  counts: { calendar: boolean; rooms: number; programmes: number; classes: number; faculty: number; subjects: number;
    sessions: number; periods_per_week: number };
  diagnostics: Diagnostic[];
}

export interface Notification {
  id: string; kind: string; title: string; body: string; link: string | null; created_at: string; read_at: string | null;
}

export interface ChangeRequest {
  id: string; kind: "AVAILABILITY" | "SESSION_MOVE" | "TIMETABLE_PUBLISH";
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED"; title: string; reason: string;
  payload: Record<string, unknown>; target_type: string; target_id: string; reviewer_role: Role;
  requested_by: { id: string; name: string; role: Role } | null; reviewed_by: { id: string; name: string } | null;
  review_comment: string | null; created_at: string; reviewed_at: string | null;
}

export interface AuditRow {
  seq: number; at: string; actor_id: string | null; actor_email: string | null; actor_role: string | null;
  action: string; category: string; outcome: string; entity: string | null; entity_id: string | null;
  summary: string; data: Record<string, unknown>; ip: string | null; request_id: string | null; hash: string;
}

export interface ConstraintItem {
  key: string; category: "Faculty" | "Rooms" | "Subjects" | "Global"; label: string; description: string;
  modes: ("HARD" | "SOFT" | "OFF")[]; mode: "HARD" | "SOFT" | "OFF"; weight: number; value: number | null;
  has_value?: boolean;
}

export interface Dashboard {
  counts: { programmes: number; subjects: number; faculty: number; rooms: number; labs: number; classes: number };
  timetable?: TimetableSummary;
  overview?: { allocated_pct: number; available_pct: number; unassigned: number; quality: number | null };
  published: { id: string; name: string; published_at: string } | null;
  pending_requests?: number;
  last_run?: { id: string; status: RunStatus; created_at: string } | null;
  recent_activity?: { action: string; summary: string; at: string; actor: string | null; category: string }[];
  users?: Record<Role, number>;
}

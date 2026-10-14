"""Role-based permissions, configurable by the admin, with hierarchical delegation.

* Every permission has a *ceiling*: the lowest role that may ever hold it (a student can never
  publish, whatever anyone configures). ADMIN always holds every permission.
* The admin edits the permission sets of COORDINATOR, FACULTY and STUDENT.
* Anyone holding ``permissions.manage`` may edit the sets of roles *below* their own — but may only
  add or remove permissions they hold themselves. So the admin decides whether coordinators may
  manage faculty/student permissions, and a coordinator (if allowed) decides whether faculty may
  manage student permissions. Lower roles can never change higher roles.
"""
from dataclasses import asdict, dataclass

from app.core.roles import RANK, Role


@dataclass(frozen=True)
class Permission:
    key: str
    group: str
    label: str
    description: str
    ceiling: Role  # lowest role that may hold it

    def allowed_for(self, role: Role) -> bool:
        return RANK[role] >= RANK[self.ceiling]


CATALOGUE: list[Permission] = [
    Permission("timetable.view_published", "Timetable", "View published timetables",
               "See published (live) timetables: your own class, or your own teaching for faculty.", Role.STUDENT),
    Permission("timetable.view_all_classes", "Timetable", "View all classes",
               "See the timetable of any class. Without it, students see only their own class.", Role.STUDENT),
    Permission("timetable.view_faculty", "Timetable", "Faculty view",
               "See any faculty member's timetable. Faculty can always see their own.", Role.STUDENT),
    Permission("timetable.view_rooms", "Timetable", "Room / Lab view",
               "See the timetable of any classroom or laboratory.", Role.STUDENT),
    Permission("timetable.export", "Timetable", "Print & export",
               "Download PDF, Excel, CSV and calendar (.ics) files.", Role.STUDENT),
    Permission("timetable.view_drafts", "Timetable", "View drafts & reports",
               "See draft timetables, generation reports and run history.", Role.FACULTY),
    Permission("timetable.generate", "Timetable", "Generate timetables",
               "Run the timetable generator and the pre-flight check.", Role.COORDINATOR),
    Permission("timetable.edit", "Timetable", "Edit drafts",
               "Create, move, lock, duplicate and delete draft timetables.", Role.COORDINATOR),
    Permission("timetable.submit", "Timetable", "Send for publishing",
               "Send a finished draft for publishing review.", Role.COORDINATOR),
    Permission("timetable.publish", "Timetable", "Publish timetables",
               "Publish directly and approve or reject publish requests.", Role.COORDINATOR),
    Permission("setup.view", "Setup", "View setup data",
               "Open calendar, programmes, subjects, faculty, rooms and constraints (read-only).", Role.FACULTY),
    Permission("setup.edit", "Setup", "Change setup data",
               "Create and change calendar, programmes, subjects, faculty, rooms, constraints and rules.",
               Role.COORDINATOR),
    Permission("reports.view", "Setup", "View reports", "Faculty workload and room utilisation.", Role.FACULTY),
    Permission("availability.request", "Requests", "Request availability changes",
               "Faculty send their own availability changes for approval.", Role.FACULTY),
    Permission("availability.edit_own", "Requests", "Change own availability directly",
               "Faculty change their own availability without approval.", Role.FACULTY),
    Permission("session.request_move", "Requests", "Request session moves",
               "Faculty ask to move one of their sessions on a published timetable.", Role.FACULTY),
    Permission("requests.review", "Requests", "Approve faculty requests",
               "Approve or reject availability and session-move requests of lower roles.", Role.COORDINATOR),
    Permission("users.view", "Users", "View users", "See the accounts of lower roles.", Role.FACULTY),
    Permission("users.create", "Users", "Add users",
               "Add accounts of lower roles (faculty may add students only).", Role.FACULTY),
    Permission("users.manage", "Users", "Manage users",
               "Deactivate, reactivate and reset passwords of lower-role accounts.", Role.FACULTY),
    Permission("permissions.manage", "Administration", "Manage permissions of lower roles",
               "Change what roles below yours may see and do (only permissions you hold).", Role.FACULTY),
    Permission("audit.view", "Administration", "View audit log",
               "Read and verify the audit trail (read-only; nobody can change it).", Role.COORDINATOR),
]
BY_KEY = {p.key: p for p in CATALOGUE}
ALL_KEYS = frozenset(BY_KEY)
ADMIN_ONLY = frozenset({"settings.system"})  # never grantable

DEFAULT_MATRIX: dict[str, list[str]] = {
    Role.COORDINATOR.value: [
        "timetable.view_published", "timetable.view_all_classes", "timetable.view_faculty", "timetable.view_rooms",
        "timetable.export", "timetable.view_drafts", "timetable.generate",
        "timetable.edit", "timetable.submit", "setup.view", "setup.edit", "reports.view", "requests.review",
        "users.view", "users.create", "users.manage",
    ],
    Role.FACULTY.value: [
        "timetable.view_published", "timetable.view_all_classes", "timetable.view_faculty", "timetable.view_rooms",
        "timetable.export", "availability.request", "session.request_move",
        "users.view", "users.create", "users.manage",
    ],
    Role.STUDENT.value: ["timetable.view_published", "timetable.export"],
}

MANAGED_ROLES = [Role.COORDINATOR, Role.FACULTY, Role.STUDENT]


def sanitize(role: Role, keys) -> list[str]:
    """Drop unknown keys and anything above the role's ceiling."""
    return sorted(k for k in set(keys) if k in BY_KEY and BY_KEY[k].allowed_for(role))


def effective(role: Role, matrix: dict[str, list[str]]) -> frozenset[str]:
    if role == Role.ADMIN:
        return ALL_KEYS | ADMIN_ONLY
    return frozenset(sanitize(role, matrix.get(role.value, DEFAULT_MATRIX.get(role.value, []))))


def manageable_roles(role: Role, perms: frozenset[str]) -> list[Role]:
    if role == Role.ADMIN:
        return list(MANAGED_ROLES)
    if "permissions.manage" not in perms:
        return []
    return [r for r in MANAGED_ROLES if RANK[r] < RANK[role]]


def catalogue_dicts() -> list[dict]:
    return [{**asdict(p), "ceiling": p.ceiling.value} for p in CATALOGUE]

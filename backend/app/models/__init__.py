from app.models.academic import (  # noqa: F401
    Batch, Break, CalendarSettings, ConstraintMode, ConstraintSetting, Faculty, FixedSession, LabType, Level,
    Programme, Room, RoomKind, StudentGroup, Subject, SubjectKind, subject_faculty,
)
from app.models.audit import AuditChainHead, AuditLog  # noqa: F401
from app.models.identity import AuthSession, Notification, OtpChallenge, User  # noqa: F401
from app.models.timetable import GenerationRun, RunStatus, Timetable, TimetableEntry, TimetableStatus  # noqa: F401
from app.models.workflow import ChangeRequest, RequestKind, RequestStatus, SystemSetting  # noqa: F401

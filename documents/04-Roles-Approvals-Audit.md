# Document 4 — Roles, Approval Workflow, Notifications & Audit Trail

*Decisions taken with the team after Documents 1–3. Implemented and covered by `backend/tests/test_api_flow.py`.*

---

## 1. Role hierarchy

```
ADMIN  >  COORDINATOR  >  FACULTY  >  STUDENT
```

| Role | Can do |
|---|---|
| **Admin** | Everything. Creates users of **any** role. Approves timetable publication. Changes system settings. Reads and verifies the audit log. |
| **Coordinator** | Manages all timetable inputs. Generates, edits, locks and regenerates timetables. Sends timetables for review. Approves faculty requests. Adds **faculty and students**. |
| **Faculty** | Views published timetables (their own by default). Requests availability changes and session moves. Adds **students only**. |
| **Student** | Views their own class's published timetable. Exports it (PDF/Excel/iCal). |

Enforced on the **server** for every route: deny by default, plus object-level checks. For example, faculty can only change their own availability and only manage students they added. The frontend hides pages and buttons a role can't use, but security never depends on the frontend.

## 2. "Whoever adds a user, the higher roles are notified"

| Who adds a user | Allowed roles to add | Who is notified |
|---|---|---|
| Admin | any | other admins |
| Coordinator | Faculty, Student | **all admins** |
| Faculty | Student | **all coordinators and admins** |

- New accounts get a **one-time temporary password**, shown once to the creator. The user must change it at first sign-in, and nothing else is reachable until they do.
- Deactivations, role changes and password resets also notify the higher roles. A privilege reduction **signs the user out everywhere** immediately.
- The last active admin can't be demoted or deactivated.

## 3. Maker–checker approvals (nothing takes effect until approved)

| Request | Raised by | Approved by | On approval |
|---|---|---|---|
| **Publish timetable** | Coordinator ("Send for review") | Admin | Re-validated, then published. Previous timetable for the same classes is archived. Everyone is notified. |
| **Availability change** | Faculty ("My Availability") | Coordinator / Admin | Applied to the faculty profile; used by the next generation. |
| **Session move** | Faculty (on a published timetable) | Coordinator / Admin | Applied to a **new draft revision** (the published version stays untouched), ready for review. |

Rules:
- **No self-approval** (separation of duties).
- **Rejection requires a reason.** The requester sees it.
- A timetable that changed after it was submitted can't be approved, because the content hash is checked.
- Drafts and in-review timetables are visible only to admins and coordinators.
- Admin-controlled switches (Settings → System): *publishing requires admin approval* (default **on**), *faculty availability changes require approval* (default **on**). If publishing approval is switched off, a coordinator publishes directly and admins are notified.

## 4. Immutable, tamper-evident audit trail

**What is logged:** every sign-in (success, failure, lockout), sign-out, OTP request, password change or reset, user change, data create/update/delete with before/after values, constraint and calendar change, generation run, manual move, lock, export, submit, approve/reject, publish, settings change, and every **denied** action (wrong role, CSRF failure, self-approval attempt). Each entry records who, role, when, IP, user agent and request ID. Secrets are automatically masked.

**Why it can't be silently altered:**
1. **Append-only by design:** the application has no update or delete code path for audit rows.
2. **Database triggers** reject any `UPDATE`, `DELETE` or `TRUNCATE` on `audit_logs`, even from someone with SQL access through the app account.
3. **HMAC hash chain:** each row stores `HMAC(key, previous_hash + row)`. Changing, deleting or re-ordering any row breaks the chain. The key is held **outside the database**, so a database administrator can't recompute a valid chain.
4. **Verify integrity:** the Audit Log page and `GET /api/v1/audit-logs/verify` re-check the whole chain and report the first broken record. Verification is itself audited.
5. **Same transaction:** the audit row is written in the same transaction as the change it describes, so neither can exist without the other.
6. **Production hardening:** the app's database role gets only `INSERT`/`SELECT` on `audit_logs`. Logs are also written as structured JSON access logs (one line per HTTP request, with request ID) for shipping to an external log store.

## 5. Notifications

In-app notification bell with unread count, polled every 30 s. Events:
- user added or changed (sent up the hierarchy);
- approval requested and decided;
- account locked (sent to admins);
- generation finished (sent to whoever started it);
- timetable published (sent to everyone).

Email delivery uses the same mailer that sends OTP codes; SMTP is configured in `.env`.

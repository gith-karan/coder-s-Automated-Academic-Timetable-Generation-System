# NFSU Academic Timetable System

Automated, conflict-free academic timetabling for National Forensic Sciences University (Problem Statement #1).

- **Engine:** Google OR-Tools CP-SAT. Every mandatory rule is guaranteed; impossible inputs are proven impossible and explained in plain English with a link to the record to fix.
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2. PostgreSQL in production, SQLite for local development.
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4, Radix UI, dnd-kit, TanStack Query. Responsive on desktop, tablet and phone, with six colour themes, light/dark mode and 12/24-hour time.
- **Security:**
  - server-side cookie sessions, Argon2id password hashing, CSRF tokens, rate limiting and account lockout;
  - configurable role permissions (Admin › Coordinator › Faculty › Student) with least-privilege defaults;
  - strict security headers (including a Content-Security-Policy);
  - a hash-chained, append-only audit log.

## Documentation

| Document | Contents |
|---|---|
| [01 · Architecture & Technology](documents/01-Architecture-and-Technology.md) | Problem, solution, architecture diagrams, scheduling engine, technology choices and rationale |
| [02 · User Guide & Role Flows](documents/02-User-Guide-and-Role-Flows.md) | Every screen, and step-by-step journeys for Admin, Coordinator, Faculty and Student |
| [03 · Security & Consistency](documents/03-Security-and-Consistency.md) | Threat model, every security control, data-integrity guarantees, OWASP mapping, verification |

## Run locally (development)

Prerequisites: Python 3.12+, Node 22+, pnpm.

```bash
# 1) Backend  (http://127.0.0.1:8000, API docs at /api/docs in development)
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip
cp .env.example .env                                # then set the passwords below
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header
# (add --reload --reload-dir app while developing; on Windows the reloader occasionally hangs — just restart)

# 2) Frontend  (http://localhost:5173) — proxies /api to the backend on the same origin
cd frontend
pnpm install
pnpm dev
```

Development `.env` (local machine only; never use these values in production):

```
NFSU_ENV=dev
NFSU_BOOTSTRAP_ADMIN_PASSWORD=<choose one>   # first admin: admin@nfsu.ac.in
NFSU_DEMO_PASSWORD=<choose one>              # password for the demo coordinator / faculty / student accounts
```

Sign in as `admin@nfsu.ac.in` and click **Load SCSDF data** on the Dashboard. This loads the Semester I 2026-27 structure of the School of Cyber Security & Digital Forensics (Gandhinagar), taken from the official class timetables:
- 4 programmes, 19 faculty and 39 subject components (with official codes and short names);
- 12 rooms, and a 10:30–17:30 day with lunch 13:30–14:30.

The assumptions (class strengths, room capacities, e-mail addresses) are documented at the top of `backend/app/seed.py`.

Demo accounts are created as well: two programme coordinators, one faculty member and one student. Their e-mail addresses are listed in `DEMO_USERS` in `backend/app/seed.py`.

To demonstrate the problem statement's "impossible timetable" example, an admin can call `POST /api/v1/demo/scenario/infeasible`:
- it leaves the faculty member who teaches `MTAI26-PC-102` with only 2 free periods, while the subject needs 3;
- `POST /api/v1/demo/scenario/reset` restores the original availability.

Demo endpoints exist only in development.

### Ready-made sample database

`backend/sampledata.db` contains the seed data above plus one generated draft timetable (85 sessions, 0 conflicts, proven optimal). To use it, copy it to `backend/data/app.db` before starting the backend:

```bash
mkdir -p backend/data && cp backend/sampledata.db backend/data/app.db
```

Account passwords are not stored in this repository (only salted Argon2id hashes are in the database); obtain them privately. Never deploy the sample database to production: create a fresh database with strong passwords instead.

## Tests and checks

```bash
cd backend && .venv/Scripts/python -m pytest -q     # 25 tests: engine acceptance, API workflow, permissions, security
cd frontend && pnpm typecheck && pnpm build
```

## Production

`deploy/Caddyfile` is a reverse-proxy configuration with:
- automatic HTTPS and HSTS;
- the security headers;
- a 2 MB request-body limit;
- serving of the built frontend (`frontend/dist`), with `/api/*` forwarded to the backend.

With `NFSU_ENV=prod` the backend refuses to start with default secrets or SQLite.

## Project layout

```
backend/app/scheduling/   pure engine: timegrid, domain, prechecks, solver (CP-SAT), validator, explain, scoring
backend/app/services/     use cases: auth, users, permissions, workflow (approvals), generation, timetables, audit
backend/app/api/v1/       thin routers + generic CRUD factory
backend/tests/            automated tests
frontend/src/components/  UI kit + shared ResourcePage / EntityForm / SlotPainter / widgets
frontend/src/features/    one folder per screen
deploy/                   production reverse-proxy configuration
documents/                architecture, user guide, security
```

Brand assets in `frontend/public/brand/` are derived from the official emblem published at nfsu.ac.in/emblem.

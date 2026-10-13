# NFSU Academic Timetable System

Automated, conflict-free academic timetabling for National Forensic Sciences University (Problem Statement #1).

- **Engine:** Google OR-Tools CP-SAT. Every mandatory rule is guaranteed; impossible inputs are proven impossible and explained in plain English.
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL (SQLite for local development).
- **Frontend:** React 19, TypeScript, Vite, Tailwind 4, Radix UI, dnd-kit, TanStack Query. Responsive and installable as an app (PWA).
- **Security:** server-side cookie sessions, Argon2id password hashing, CSRF tokens, role-based access (Admin > Coordinator > Faculty > Student), rate limiting and lockout, strict security headers (CSP and others), and a hash-chained, append-only audit log.

Design documents are in [`documents/`](documents/).

## Run locally (development)

Prerequisites: Python 3.12+, Node 22+, pnpm.

```bash
# 1) Backend  (http://127.0.0.1:8000, API docs at /api/docs)
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip
cp .env.example .env                                # then set the passwords below
.venv/Scripts/python -m uvicorn app.main:app --reload --reload-dir app

# 2) Frontend (http://127.0.0.1:5173). Proxies /api to the backend, same origin.
cd frontend
pnpm install
pnpm dev
```

Development `.env` (local machine only; never use these values in production):

```
NFSU_ENV=dev
NFSU_BOOTSTRAP_ADMIN_PASSWORD=<choose one>   # first admin: admin@nfsu.ac.in
NFSU_DEMO_PASSWORD=<choose one>              # demo coordinator / faculty / student
```

Sign in as `admin@nfsu.ac.in` and click **Load NFSU demo data** on the Dashboard. This loads the real
**SCSDF Semester I 2026-27** data taken from the official class timetables (effective 12/10/2026):
4 programmes (M.Tech. AI & DS (Cyber Security), M.Sc. Cyber Security, B.Tech.–M.Tech. CSE (Cyber Security),
M.Sc. DFIS), 19 faculty, their subjects with official codes, 12 rooms and the 10:30–17:30 day with lunch
13:30–14:30. See the docstring in `backend/app/seed.py` for the assumptions (class strengths, room capacities,
e-mail addresses).

| Role | Account |
|---|---|
| Coordinator, M.Tech. AI & DS | Ahlad Kumar (`ahlad.kumar@nfsu.ac.in`) |
| Coordinator, M.Sc. Cyber Security | Pruthvish Rajput (`pruthvish.rajput@nfsu.ac.in`) |
| Faculty | Ms. Krupali Panchal (`krupali.panchal@nfsu.ac.in`) |
| Student (M.Sc. DFIS Sem I) | `student.demo@nfsu.ac.in` |

To demo the problem statement's "impossible timetable" example, an admin can call `POST /api/v1/demo/scenario/infeasible`. Dr. Vijeta Khare then has only 2 free periods, while MTAI26-PC-102 needs 3. `.../scenario/reset` restores her availability.

The earlier mock dataset is archived in `backend/backups/`.

### Ready-made sample database

`backend/sampledata.db` is a snapshot of the development database: the SCSDF data plus a generated timetable
(85 sessions, 0 conflicts). To use it, copy it to `backend/data/app.db` before starting the backend:

```bash
mkdir -p backend/data && cp backend/sampledata.db backend/data/app.db
```

The admin and demo account passwords are not stored in this repository; get them from the team privately.
Never deploy this sample database to production: create a fresh database and strong passwords instead.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q     # engine acceptance tests + end-to-end API/security flow
cd frontend && pnpm typecheck && pnpm build
```

## Project layout

```
backend/app/scheduling/   pure engine: timegrid, domain, prechecks, solver (CP-SAT), validator, explain, scoring
backend/app/services/     use cases: auth, users, workflow (approvals), generation runner, timetables, audit
backend/app/api/v1/       thin routers + generic CRUD factory
frontend/src/components/  UI kit + shared ResourcePage / EntityForm / SlotPainter / widgets
frontend/src/features/    one folder per page
```

Brand assets in `frontend/public/brand/` are derived from the official emblem published at nfsu.ac.in/emblem.

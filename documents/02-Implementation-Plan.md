# Automated Academic Timetable Generation System
## Document 2 — Implementation Plan (Domain, Engine, API, UI/UX, Delivery)

Read `01-Requirements-Architecture-TechStack.md` first. Codes such as **H-4** and **R-3** refer to the traceability matrix in that document.

---

## 1. Repository layout (monorepo)

```
Pr1-solution/
├── documents/                    # these plans, ADRs, demo script
├── backend/
│   ├── app/
│   │   ├── main.py               # app factory, middleware, routers
│   │   ├── core/                 # config, db, security, errors, logging, rate-limit
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic DTOs (Create / Update / Read per entity)
│   │   ├── repositories/         # generic Repository[T] + specific queries
│   │   ├── services/             # use cases (transactions, authorization, audit)
│   │   ├── api/v1/               # routers (thin) + generic CRUD router factory
│   │   ├── scheduling/           # PURE engine: no DB, no HTTP
│   │   │   ├── domain.py         # Problem, SessionUnit, Slot, Placement, Solution
│   │   │   ├── timegrid.py       # calendar → periods, contiguity, time-range → periods
│   │   │   ├── builder.py        # DB entities → Problem (session-unit expansion)
│   │   │   ├── prechecks.py      # layer-2 diagnostics (capacity / pigeonhole)
│   │   │   ├── solver.py         # CP-SAT model
│   │   │   ├── explain.py        # layer-3 diagnostics (core + blocking analysis)
│   │   │   └── validator.py      # hard-rule checker (shared by 4 features)
│   │   ├── jobs/                 # JobRunner interface: ProcessPool impl, arq impl
│   │   └── exports/              # xlsx, pdf, csv, ics renderers (share one view model)
│   ├── alembic/                  # migrations
│   ├── seeds/                    # demo datasets (PS example, infeasible variant, large)
│   └── tests/                    # unit, scenario, property, API, authz-matrix
├── frontend/
│   ├── src/
│   │   ├── app/                  # router, providers, layout shell
│   │   ├── api/                  # GENERATED client + query-key factory
│   │   ├── components/ui/        # shadcn primitives (owned code)
│   │   ├── components/shared/    # DataTable, EntityDrawer, WeekGrid, StatusBadge…
│   │   ├── features/<domain>/    # calendar, rooms, programmes, faculty, subjects,
│   │   │                         # constraints, generate, timetable, publish, admin
│   │   ├── hooks/ lib/ styles/
│   └── e2e/                      # Playwright
├── deploy/                       # docker-compose.yml, Caddyfile, .env.example
└── .github/workflows/            # CI: lint, type-check, test, audit, build
```

---

## 2. Domain model

### 2.1 Entities (database tables)

| Table | Key fields | Notes |
|---|---|---|
| `users` | id (UUID), email (unique), name, password_hash, role, is_active, mfa_secret?, failed_logins, locked_until | Roles: ADMIN, COORDINATOR, FACULTY, VIEWER |
| `auth_sessions` | id, token_hash, user_id, csrf_hash, created_at, last_seen_at, expires_at, ip, user_agent | Server-side sessions, revocable |
| `audit_logs` | id, actor_id, action, entity, entity_id, before JSON, after JSON, ip, at | Append-only |
| `calendar_settings` | working_days int[], day_start, day_end, period_minutes | One row per tenant |
| `breaks` | name, start_time, end_time, days int[] | e.g. Lunch 13:00–13:45 |
| `lab_types` | id, name (unique) | "Computer Lab", "Forensic Lab", "Chemistry Lab"… |
| `rooms` | code (unique), name, kind (CLASSROOM/LAB), lab_type_id?, capacity, building, is_active, unavailable JSON[time-ranges] | |
| `programmes` | code, name, level | "M.Sc. DFIS" |
| `student_groups` | programme_id, semester, section, strength | unique(programme, semester, section) |
| `batches` | group_id, name, strength | Σ batch strength should equal group strength (warning) |
| `faculty` | code, name, email, designation, max_per_day?, max_per_week?, user_id?, availability JSON, preferences JSON | Availability stored as **time ranges**, not period indices, so changing period length doesn't corrupt it |
| `faculty_commitments` | faculty_id, day, start_time, end_time, reason | Time blocked outside this timetable (I-6) |
| `subjects` | code (unique), name, programme_id, semester, kind (THEORY/PRACTICAL), periods_per_week, sessions_per_week, consecutive_periods, lab_type_id?, default_faculty_ids | THEORY uses periods_per_week; PRACTICAL uses sessions × consecutive |
| `teaching_assignments` | subject_id, group_id, batch_id?, faculty_ids | Optional override of the default faculty for a section or batch |
| `fixed_sessions` | subject_id, group_id, batch_id?, day, start_time, room_id? | Pinned sessions (I-7, H-8) |
| `constraint_settings` | key, mode (HARD/SOFT/OFF), weight, params JSON | Spread, group daily max, theory-in-lab fallback, preferred-slot weight… |
| `timetables` | id, name, status (DRAFT/PUBLISHED/ARCHIVED), version, parent_id, quality_score, input_hash, row_version, created_by, published_by, published_at | |
| `timetable_entries` | timetable_id, session_key, subject_id, group_id, batch_id?, faculty_ids, room_id, day, start_period, length, locked | `session_key` is stable across regenerations |
| `generation_runs` | timetable_id, status, mode, options, stats JSON, diagnostics JSON, started_at, finished_at, requested_by | Status: QUEUED, RUNNING, SUCCESS, INFEASIBLE, PRECHECK_FAILED, TIMEOUT, FAILED |

All tables have `id UUID`, `created_at`, `updated_at` and `tenant_id`, which is reserved for multi-campus use.

### 2.2 Session-unit expansion (builder)

The solver doesn't schedule "subjects". It schedules **session units**:

```
for subject S (programme P, semester M):
  for each group G in (P, M):
    if S.kind == THEORY:
      create S.periods_per_week units:
        length 1, audience = whole G, room kind = CLASSROOM, capacity ≥ G.strength
    if S.kind == PRACTICAL:
      for each batch B of G (or G itself if no batches):
        create S.sessions_per_week units:
          length = S.consecutive_periods, audience = B,
          room kind = LAB with lab_type = S.lab_type, capacity ≥ B.strength
    faculty = teaching_assignment(S, G, B) ?? S.default_faculty
    session_key = f"{S.code}:{G.id}:{B.id or '-'}:{n}"
```

The PS example (M.Sc. DFIS Sem I) becomes 3 theory units (length 1, audience = whole class, 40 seats) plus 2 practical units (length 2, one per batch of 20, lab).

### 2.3 Audience atoms (rule H-4)

Each group is split into **atoms**: its batches, or the group itself if it has none.
- A whole-class session uses **all** atoms of the group.
- A batch session uses **only its own** atom.
- Constraint: *each atom is used by at most one session per period.*

This one rule gives both required behaviours: a whole-class lecture can never overlap any batch practical, and Batch A and Batch B can still have practicals at the same time in different labs.

---

## 3. Scheduling engine

### 3.1 Time grid

Inputs are working days, day_start, day_end, period_minutes and breaks. Periods are generated per day by stepping `period_minutes` from `day_start`. When a period would overlap a break, generation jumps to the end of the break. Two periods are **contiguous** only if one ends exactly when the next starts, so a practical can't span lunch (H-1, H-6).
Time ranges (availability, commitments, room blocks) map to period sets by overlap: a period is *available* only if it lies fully inside an availability window and touches no blocked range.

### 3.2 CP-SAT formulation

**Sets:** session units *S*, days *D*, periods *Pₐ*, rooms *R*, faculty *F*, atoms *A*.
For each unit *s*: length *Lₛ*, faculty set *Fₛ*, atom set *Aₛ*, candidate rooms *Rₛ* (kind / lab type / capacity, H-5, H-6), and candidate starts *Tₛ* = {(d,p) | p…p+Lₛ−1 contiguous, all inside working hours, all available for every f ∈ Fₛ} (H-1, H-2).

**Decision variables:** `x[s,d,p,r] ∈ {0,1}` only for feasible combinations (room r free for all covered periods). Domain filtering removes most variables before solving.
`y[s,d,p] = Σᵣ x[s,d,p,r]` (start indicator, a linear expression rather than a new variable).

**Hard constraints**

| Rule | Constraint |
|---|---|
| H-7 every session scheduled | `Σ x[s,·,·,·] = 1` for every s |
| H-3 room | ∀ r,d,q: Σ of x covering (d,q) in room r ≤ 1 |
| H-3 faculty | ∀ f,d,q: Σ of y covering (d,q) for units taught by f ≤ 1 |
| H-3/H-4 students | ∀ atom a,d,q: Σ of y covering (d,q) for units using a ≤ 1 |
| I-7 daily limit | ∀ f,d: Σ Lₛ·y[s,d,·] ≤ max_per_day(f); same per group if enabled |
| H-8 fixed / locked | `y[s,d₀,p₀] = 1` (and room fixed if specified) |

**Soft constraints (objective — minimise weighted penalty)**

| Preference | Term |
|---|---|
| Faculty preferred slots | −w · Σ y on preferred slots |
| Faculty "rather not" slots | +w · Σ y on disliked slots |
| Spread theory across days | excess = max(0, count(subject,group,day) − 1); +w · excess |
| Avoid first/last period overload (configurable) | +w · y on edge periods |
| Stability on regenerate (R-3) | −w · Σ y[s, previous slot of s]; previous solution also passed as a **solution hint** |

**Symmetry breaking:** units of the same (subject, audience) are interchangeable, so we require `start_index(unitₖ) < start_index(unitₖ₊₁)`. This greatly reduces search time.

**Solver parameters:** `num_workers = CPU count`, `max_time_in_seconds` (default 30, admin-configurable), fixed `random_seed` for reproducible results, and progress through a solution callback (objective, bound, elapsed) streamed over SSE.

**Scale fallback (if ever needed):** two-phase solve. Phase 1 assigns times with aggregate room-capacity constraints per room class; phase 2 assigns rooms per time slot (a bipartite matching).

### 3.3 Quality score
`quality = 100 × (1 − achieved_penalty / worst_case_penalty)`, with a per-preference breakdown so the coordinator can see *why* a draft scored 87 and not 95.

### 3.4 Validator (single source of truth)
`validate(problem, placements) → list[Violation]`. Each `Violation` has `code`, `severity` (HARD/SOFT), `message`, and the entity and entry IDs involved. It implements every rule H-1…H-8 independently of the solver. It is used in four places:
1. after every solve, as a safety net; a solver bug can never reach the user;
2. on every manual move (R-2) — `PATCH` returns `409` with the violations;
3. the **move-options heatmap**, which checks a dragged entry against all (day, period, room) cells;
4. the **publish gate** (R-4), which requires zero HARD violations and zero unassigned sessions.

### 3.5 Diagnosing an impossible timetable (F-1…F-3) — three layers

**Layer 1 — Input validation (immediate, while typing).** Pydantic and cross-entity checks. Examples: batch strengths don't add up to the class strength; practical length is longer than the longest break-free block; subject has no faculty; lab type has no lab.

**Layer 2 — Pre-flight checks (milliseconds, before solving).** Counting arguments. Each check has a stable code and a message template:

| Code | Check | Example message |
|---|---|---|
| `FACULTY_AVAIL_LT_REQUIRED` | periods a subject needs > periods its faculty is available | *"Subject DFIS103 requires 3 weekly periods, but its assigned faculty member Dr. A. Rao is available for only 2 periods."* |
| `FACULTY_OVERLOADED` | total load of a faculty member > their available periods | *"Dr. Rao is assigned 18 periods but is available for 14."* |
| `FACULTY_DAILY_LIMIT` | load > max_per_day × available days | |
| `NO_ROOM_FOR_STRENGTH` | no classroom with capacity ≥ class strength | *"M.Sc. DFIS Sem I-A has 65 students; the largest classroom seats 60."* |
| `NO_LAB_OF_TYPE` / `NO_LAB_CAPACITY` | no lab of the required type, or none big enough for the batch | |
| `NO_CONSECUTIVE_WINDOW` | faculty and suitable labs share no window of L consecutive periods | *"Practical DFIS151 needs 3 consecutive periods; Dr. Rao's availability never has 3 in a row."* |
| `GROUP_OVERLOADED` | weekly periods required by a class/batch > periods in the week | |
| `LAB_TYPE_OVERSUBSCRIBED` | lab periods needed of a type > lab periods available | |
| `FIXED_SESSION_CONFLICT` | two pinned sessions collide, or a pin is outside hours or availability | |

**Layer 3 — Solver diagnosis (when the model is infeasible after pre-checks pass).**
- **Unsat core:** every "session must be scheduled", pin and daily-limit constraint gets an *assumption literal*. CP-SAT's `SufficientAssumptionsForInfeasibility()` returns a small set that cannot hold together. We then name the resource those sessions share: *"These 7 sessions all need Dr. Rao or Lab-2 on Tuesday–Thursday afternoons, which have only 6 free periods."*
- **Best partial schedule:** re-solve while maximising the number of sessions placed. This gives a draft marked **INFEASIBLE** (it can't be published) and the list of **unassigned sessions**.
- **Blocking analysis:** for each unassigned session, every candidate slot is checked with the validator and the blockers are summarised: *"Every slot Dr. Rao is free, M.Sc. DFIS Sem I is already in DFIS101/DFIS102."*

Every diagnostic includes `fix_links` (for example `/faculty/{id}#availability`), which the UI shows as **"Fix →"** buttons.

### 3.6 Lock & regenerate (R-3)
Locked entries become fixed constraints. Unlocked units are re-solved with the stability term and the hint, so the result is *as close as possible to the previous draft*. The result screen shows "*12 sessions moved*" with a diff.

---

## 4. REST API (v1)

Conventions: JSON; RFC 9457 `application/problem+json` errors; cursor pagination; `ETag`/`If-Match` for optimistic concurrency on timetable entries; every route has a declared role requirement.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` · `POST /auth/mfa/enroll` · `POST /auth/mfa/verify` · `POST /auth/password` |
| Users (admin) | CRUD `/users` |
| Calendar | `GET/PUT /calendar` · `GET /calendar/grid` (computed periods for preview) |
| Resources (generic CRUD factory) | `/lab-types` · `/rooms` · `/programmes` · `/groups` · `/groups/{id}/batches` · `/faculty` · `/faculty/{id}/commitments` · `/subjects` · `/subjects/{id}/assignments` · `/fixed-sessions` · `/constraints` |
| Availability | `PUT /faculty/{id}/availability` (faculty may edit their own) · `PUT /rooms/{id}/availability` |
| Import | `GET /import/templates/{entity}.xlsx` · `POST /import/{entity}` (dry-run preview, then commit) |
| Readiness | `GET /readiness` → setup completeness + layer-1/2 diagnostics without solving |
| Timetables | `GET/POST /timetables` · `GET /timetables/{id}` · `POST /timetables/{id}/duplicate` · `DELETE` (drafts only) |
| Generation | `POST /timetables/{id}/generate` `{mode: full\|unlocked, time_limit}` → run · `GET /runs/{id}` · `GET /runs/{id}/events` (SSE) · `POST /runs/{id}/cancel` |
| Entries | `GET /timetables/{id}/entries?view=group\|faculty\|room&ref=` · `PATCH /timetables/{id}/entries/{eid}` · `POST …/{eid}/lock` · `GET …/{eid}/options` (heatmap) · `POST /timetables/{id}/validate` |
| Publish | `POST /timetables/{id}/publish` · `GET /timetables/{a}/diff/{b}` |
| Export | `GET /timetables/{id}/export?format=pdf\|xlsx\|csv\|ics&view=&ref=` |
| Public | `GET /published/current` · `GET /ical/{token}.ics` (secret, revocable token) |
| Ops | `GET /healthz` · `GET /readyz` · `GET /audit-logs` (admin) |

---

## 5. Frontend: information architecture & page design

### 5.1 Navigation shell
- **Left sidebar**, collapsible to icons; on mobile it becomes a **bottom tab bar**:
  - **Overview** — Dashboard
  - **Setup** — Calendar · Rooms & Labs · Programmes · Faculty · Subjects · Constraints
  - **Schedule** — Generate · Timetables
  - **Admin** — Users · Audit log · Settings
- **Top bar:** breadcrumb, global search / **command palette (Ctrl/⌘ K)**, light/dark toggle, profile menu.
- **The menu adapts to role:** FACULTY users see *My Timetable* and *My Availability*; VIEWER users see *Published Timetables* only.
- Each page does one job, with no dumping of everything on one screen. Details open in **side drawers** so the list stays in context.

### 5.2 Page-by-page

| Page | Purpose | Key UX |
|---|---|---|
| **Login** | Sign in | Minimal card, password visibility toggle, MFA step, generic error, lockout notice |
| **Dashboard** | "Where am I?" | **Setup progress stepper** (Calendar → Rooms → Programmes → Faculty → Subjects → Generate) with ✓ / ⚠ per step; KPI tiles (sessions to schedule, faculty load %, room utilisation %); latest runs; published-version card; "Load demo data" for first-time users |
| **Academic Calendar** | I-1 | Working-day chips (Mon–Sat); time pickers; period-length stepper; break list; **live preview of the period grid** that updates as you type |
| **Rooms & Labs** | I-2 | Data table (search, filter by type/lab type/capacity, sort); side drawer form; **availability painter** (click/drag on the week grid to block times); bulk Excel import |
| **Programmes** | I-3 | **Tree view** Programme → Semester → Section → Batches; inline strength edits; warning badge when batch sums don't match |
| **Faculty** | I-6 | List with load bar (assigned/available periods); profile drawer with tabs *Details · Availability · Commitments · Preferences · Timetable*. **Availability painter** with three brushes: Available, Unavailable, Preferred |
| **Subjects** | I-4, I-5 | Grouped by Programme/Semester; Theory/Practical segmented control shows only relevant fields (periods/week vs sessions × consecutive + lab type); faculty multi-select; "Override per section/batch" expander |
| **Constraints** | I-7, I-8 | Two clearly separated cards: **Mandatory** (lock icon, explains it can never be broken) and **Preferences** (weight slider Off · Low · Medium · High); pinned-sessions list with "Add fixed session" |
| **Generate** | Run the engine | **Readiness check** first: green list, or problems with "Fix →". Then the *Generate* button → live progress (elapsed, sessions placed, best quality so far) through SSE, with Cancel |
| **Run Result / Infeasibility Report** | F-1…F-3 | Large status banner (✅ Success / ⛔ Not possible). Problems grouped by type and sorted by severity, each in plain English with linked entities and **Fix →**. Unassigned-sessions table. "View best partial draft (not publishable)" |
| **Timetable Workspace** | R-1…R-3 | View switcher **Programme/Class · Faculty · Room** with an entity picker. Week grid with colour-coded subject chips (code, faculty initials, room). **Drag & drop**: on pickup, every cell shows ✓ / ⚠ / ✕ from the options heatmap, with the reason on hover. Lock toggle per chip, **"Lock all visible"**, **"Regenerate unlocked"**, undo/redo, side panel with conflicts and the quality-score breakdown. Keyboard: select a chip and use arrow keys to move it |
| **Versions** | R-4 | List of drafts and published versions; **compare two** (moved / added / removed highlighted); Publish button (disabled with the reason until valid); confirmation shows what changes for whom |
| **Published view / My Timetable** | R-5 | Clean read-only grid; **Print** (dedicated print layout); export PDF, Excel, CSV, ICS; "Subscribe in Google/Outlook" link; works offline (PWA) |
| **Users / Audit log / Settings** | Admin | Role management, sessions, MFA enforcement; filterable audit trail; solver time limit; institution branding |

### 5.3 Design system
- **Visual style:** clean and modern. Neutral surfaces, **one brand accent**, 8-px spacing scale, 12-px radius, soft elevation, Inter / Geist typeface, tabular numbers for times.
- **Subject colours:** auto-assigned from a colour-blind-safe categorical palette, consistent in every view. Status is never shown by colour alone (icon + text as well).
- **States everywhere:** skeleton loaders, illustrated empty states with a single call to action, inline field errors, toasts with **Undo** instead of "Are you sure?" dialogs where reversible.
- **Density toggle** (comfortable / compact) for big grids; **dark mode**; reduced-motion support.
- **Responsive:** grid scrolls horizontally with sticky day/period headers on tablets; on phones the timetable switches to a **day-agenda list**.

### 5.4 Frontend architecture
- **Generated API client** from `/openapi.json` (`pnpm gen:api`): no hand-written fetch code or duplicated types.
- **TanStack Query** with a query-key factory per resource; optimistic updates on drag, rolled back on `409`.
- **Route-level code splitting** (`React.lazy`); the timetable workspace and exports load only when opened.
- **zod schemas** mirror backend rules for instant feedback; the server remains the authority.

---

## 6. Code-reuse strategy

| Reused piece | Used by |
|---|---|
| Backend `Repository[T]` + `crud_router()` factory | All 10+ resource endpoints: one implementation of list, filter, paginate, create, update, delete, audit and RBAC |
| `validator.py` | Solver post-check, manual edit, heatmap, publish gate |
| `timegrid.py` | Calendar preview, builder, exports, availability mapping |
| Timetable **view model** (`build_grid(view, ref)`) | API response, PDF, Excel, CSV, ICS, print |
| Frontend `<WeekGrid>` | Calendar preview, faculty/room availability painters, timetable workspace (3 views), published view, print |
| `<DataTable>` + `<EntityDrawer>` + `useResource()` hook | Rooms, programmes, faculty, subjects, users, constraints |
| Generated API types | Every frontend call |

---

## 7. Testing strategy

| Level | What | Tool |
|---|---|---|
| Unit | timegrid, builder expansion, each pre-check, each validator rule | pytest |
| Scenario | **PS example (DFIS)** → success with 3 + 2 sessions; **infeasible variant** → exact DFIS103-style message; lock & regenerate keeps locked entries | pytest |
| Property-based | Random valid instances: every solver result passes the validator; reported infeasibility is confirmed by the pre-check or the core | Hypothesis |
| API | CRUD, auth flows, `409` on conflicting move, publish gate | pytest + httpx |
| Security | **Authorization matrix**: every route × every role → expected allow/deny; CSRF required; rate limit triggers | pytest |
| Frontend | components (WeekGrid, forms) | Vitest + Testing Library |
| E2E | login → load demo → generate → drag move → lock → regenerate → publish → export | Playwright |
| Performance | large seed (300+ units) solves within target | pytest marker `slow` |

CI runs lint, type checks, tests, `pip-audit`, `pnpm audit` and the build on every push.

---

## 8. Scope (MoSCoW) — protects the demo

| Must (demo-critical) | Should | Could | Won't (this hackathon) |
|---|---|---|---|
| All inputs I-1…I-8; CP-SAT engine with H-1…H-8; 3-layer diagnostics; 3 views; drag & drop with validation; lock & regenerate; drafts + publish; print + PDF/Excel export; auth + RBAC + security headers; demo seed | Move-options heatmap; quality score; version diff; ICS export; Excel import; dark mode; PWA install | MFA; faculty self-service availability; email notifications; iCal subscription URLs | SSO, multi-campus tenancy, electives across sections, exam timetabling |

---

## 9. Delivery phases

| Phase | Backend | Frontend | Exit criterion |
|---|---|---|---|
| **P0 Foundation** | Project skeleton, config, DB, migrations, auth (sessions, CSRF, RBAC), security middleware, error format, health checks | Vite + Tailwind + shadcn setup, app shell, login page, design tokens | Login works end to end |
| **P1 Inputs** | Generic CRUD factory; all input entities; calendar grid; readiness endpoint; demo seeds | Setup pages + WeekGrid painter | Demo data visible in all setup pages |
| **P2 Engine** | timegrid, builder, prechecks, CP-SAT solver, validator, explain; job runner + SSE; scenario tests green | Generate page + Run Result / Infeasibility Report | PS example generates; infeasible variant explained |
| **P3 Review** | Entries API, PATCH + 409, options heatmap, lock, regenerate-unlocked with stability | Timetable workspace with three views, drag & drop | Manual move blocked with a reason; regenerate keeps locks |
| **P4 Publish & export** | Versions, publish gate, diff, PDF/Excel/CSV/ICS | Versions page, published view, print CSS | Published PDF printed |
| **P5 Hardening & polish** | Rate limits, audit log, authz-matrix tests, Docker Compose + Caddy, perf run | Accessibility pass, empty/loading states, PWA, mobile layout | Lighthouse ≥ 90; E2E green |

---

## 10. Demo script (≈ 5 minutes)

1. Log in as coordinator → Dashboard shows an empty setup stepper → **Load demo data**.
2. Quick tour: Calendar preview (lunch break visible), DFIS programme tree with 2 batches, faculty availability painter.
3. **Generate** → readiness all green → solved live in about 2 s → quality 94.
4. Switch views: Class → Faculty → Lab. Batch A and B practicals run in parallel; the whole-class lecture is never at the same time.
5. Drag a lecture: the heatmap shows red cells with "Dr. Rao unavailable". Drop on green → saved.
6. Lock 3 sessions → **Regenerate unlocked** → "*4 sessions moved*", locks kept.
7. Break it on purpose: set Dr. Rao to 2 available periods → Generate → ⛔ *"Subject DFIS103 requires 3 weekly periods, but its assigned faculty member is available for only 2 periods."* → **Fix →** jumps to the painter.
8. Fix → regenerate → **Publish** → export PDF and ICS → open on a phone (installed PWA).
9. 30-second security slide: OWASP mapping, cookie sessions, RBAC matrix tests.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Solver slow on a large instance | Domain filtering, symmetry breaking, time limit + best-found, two-phase fallback (§3.2) |
| Infeasibility explanations too technical | Layer-2 checks cover most real causes with hand-written sentences; layer 3 is summarised by shared resource |
| Unstable internet during the event | Pre-download Python wheels and the pnpm store; vendored fonts and icons; no CDN dependencies at runtime |
| Scope creep | MoSCoW table above; Must items first, demo rehearsed after P3 |
| Frontend/backend contract drift | OpenAPI-generated client; CI fails on type mismatch |

---

## 12. Open questions for the team
1. How long is the hackathon, and is a live deployment (public URL) expected, or a local demo?
2. Product name and branding colours?
3. Should faculty log in themselves (self-service availability), or does only the coordinator use the app?
4. Is there a real sample dataset from the university (room list, faculty list) we can seed?

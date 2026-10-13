# How Our Timetable Gets Made — Constraint Solvers Explained Simply

*A standalone guide for the team (and for judges). No prior knowledge needed.*

---

## 1. The problem in one sentence

We have to put every class into a **day + time + room** so that **nobody is in two places at once** and **every rule is respected**.

That sounds easy. It isn't, because the number of possible arrangements explodes.

> **Example:** The M.Sc. DFIS example has just **5 sessions** (3 lectures + 2 batch practicals).
> With 35 periods a week (5 days × 7 periods) and 10 rooms, each session has about 350 possible places.
> 5 sessions → 350⁵ ≈ **5 trillion** combinations.
> A real university term has **300+ sessions**. The number of combinations has more digits than there are atoms in the universe.

Trying every combination is impossible, even for a supercomputer. We need something smarter. That's a **constraint solver**.

---

## 2. What is a constraint solver? (The Sudoku analogy)

You already know how to solve **Sudoku**:

- **Variables:** the empty cells.
- **Possible values:** digits 1–9.
- **Constraints (rules):** each row, column and box has each digit once.

You don't try all combinations. You **reason**: "This row already has 5, 7 and 9, so this cell can only be 2 or 4." Each deduction **removes options**. When stuck, you **guess**. If the guess leads to a contradiction, you **undo it and learn** not to make that mistake again.

**A constraint solver is a program that does exactly this, extremely fast and without mistakes.**

You don't tell it *how* to solve the problem. You only **describe the problem**:

| You describe… | In Sudoku | In our timetable |
|---|---|---|
| **Variables** — what to decide | the digit in each cell | which day, period and room each session gets |
| **Constraints** — rules that must never break | no repeated digit in a row | no faculty, room or class in two places at once |
| **Objective** (optional) — what counts as "better" | — | honour preferred slots, spread subjects over the week |

The solver then finds an answer that follows **every** rule, or **proves** that no such answer exists.

This style of programming is called **declarative**: *"Here are the rules; find me an answer."* Ordinary code is **imperative**: *"Do step 1, then step 2…"*

---

## 3. What is OR-Tools CP-SAT?

| | |
|---|---|
| **OR-Tools** | A free, open-source optimisation toolkit made by **Google** ("OR" = Operations Research, the science of planning and scheduling). Licence: Apache 2.0, free for any use. |
| **CP-SAT** | The constraint solver inside OR-Tools. **CP** = Constraint Programming, **SAT** = Boolean Satisfiability. It combines both techniques. |
| **Track record** | Has repeatedly won gold medals in the **MiniZinc Challenge**, the international competition for constraint solvers. Used in real industry for scheduling, rostering, logistics and production planning. |
| **Language** | Written in C++ (fast). We use it from **Python**, which is why our backend is Python. |

### How CP-SAT thinks (simplified)

1. **Propagation, the Sudoku reasoning.** "Dr. Sharma is busy Monday 10:00, so DFIS101 cannot be Monday 10:00." Each rule removes impossible options from every session. Often this alone removes 90 %+ of the choices.
2. **Smart guessing.** When reasoning alone gets stuck, it tries a choice (for example "DFIS101 → Tuesday 09:00") and continues reasoning.
3. **Learning from mistakes.** If a guess leads to a dead end, it works out *why* and writes down a new rule, such as "never put DFIS101 and DFIS151-B1 both on Tuesday morning". It never repeats that mistake anywhere in the search. This is called **conflict-driven clause learning** and is what makes modern solvers so fast.
4. **Many strategies at once.** On a multi-core CPU, CP-SAT runs several different search strategies in parallel and shares what each learns. One strategy finds a good timetable quickly; others try to improve it or prove it's the best.
5. **Improving.** After finding a valid timetable, it keeps searching for a *better* one (fewer broken preferences) until it proves the current one is optimal or the time limit runs out.

The result is one of four answers:

| Solver answer | Meaning | What our app shows |
|---|---|---|
| **OPTIMAL** | Valid timetable, and provably the best by our preference score | ✅ Success, quality score |
| **FEASIBLE** | Valid timetable; might be improvable with more time | ✅ Success, quality score |
| **INFEASIBLE** | **Mathematically proven** that no valid timetable exists | ⛔ Clear explanation of *why* + what to fix |
| **UNKNOWN** | Time limit reached before an answer | ⏱ "Try a longer time limit or relax a constraint" |

The **INFEASIBLE** answer is the key one for us. The problem statement (Section 3) requires that impossible inputs are reported clearly and never shown as a successful timetable. Only an exact solver can *prove* impossibility.

---

## 4. Our timetable as a CP-SAT model (plain English)

### Step 1 — Break subjects into "sessions"
The solver doesn't schedule subjects; it schedules individual **sessions**:

| Coordinator enters | Becomes these sessions |
|---|---|
| DFIS101 (Theory, 3 periods/week) for M.Sc. DFIS Sem I (40 students) | 3 sessions × 1 period, whole class, needs a classroom with ≥ 40 seats |
| DFIS151 (Practical, 1 session × 2 consecutive periods, per batch), Batches B1 & B2 (20 each) | 1 session for B1 + 1 session for B2, each 2 periods long, needs a Digital Forensics Lab with ≥ 20 seats |

### Step 2 — Variables: yes/no questions
For every session, every possible start time, and every suitable room, the solver gets one **yes/no switch**:

> *"Does DFIS101 lecture #1 start on **Tuesday, period 1**, in **Room SCSDF-101**?"* → yes / no

Impossible switches are never created at all. There is no switch for a time when the faculty is unavailable, for a lab too small for the batch, or for a 2-period practical that would cross the lunch break. This filtering alone keeps the problem small.

### Step 3 — Rules (constraints)
Each of the problem statement's mandatory rules becomes a simple counting rule:

| PS mandatory rule | How we tell the solver |
|---|---|
| Every subject gets all its weekly periods | For each session: **exactly one** of its switches is "yes" |
| No faculty member in two places | For each faculty member and each period: **at most one** "yes" among their sessions |
| No room double-booked | For each room and each period: **at most one** "yes" |
| No student group in two places | For each student group and each period: **at most one** "yes" |
| A lecture never overlaps a practical of any batch of that class | A lecture "uses" **both** B1 and B2; a B1 practical uses only B1. Each batch: at most one session per period. B1 and B2 *can* have practicals at the same time, but never during their class lecture |
| Within working hours, avoid breaks | Switches outside hours or crossing a break are never created |
| Faculty only when available | Switches at unavailable times are never created |
| Room capacity ≥ students | Switches for rooms that are too small are never created |
| Practicals in a suitable lab, consecutive periods | Only labs of the right type; only start times with enough back-to-back periods |
| Fixed / locked sessions stay put | Their switch is forced to "yes" |
| Daily teaching limit | Sum of "yes" for a faculty member on a day ≤ limit |

### Step 4 — Preferences (the "nice to haves")
Preferences are **not** rules; they are **penalty points** the solver tries to minimise:

| Preference | Penalty |
|---|---|
| Faculty prefers mornings | +points when a session lands outside their preferred slots |
| Don't put the same subject twice on one day | +points for each extra period on the same day |
| Avoid the very last period of the day | +a small number of points |
| When regenerating, don't move things unnecessarily | +points for each session that moves from its old slot |

The coordinator chooses **Hard / Soft / Off** for these on the Constraints page. That is how we meet the PS requirement to *"distinguish mandatory constraints from preferences."*

### Step 5 — Solve
CP-SAT flips the switches and returns the timetable with the fewest penalty points that breaks **zero** rules.

### What the code looks like (tiny example)
```python
from ortools.sat.python import cp_model

model = cp_model.CpModel()

# Yes/no switch: "does session S start at slot T in room R?"
x = {}
for s in sessions:
    for t in allowed_times(s):        # only times the faculty is free
        for r in suitable_rooms(s):   # only rooms big enough and of the right type
            x[s, t, r] = model.NewBoolVar(f"{s}_{t}_{r}")

# Rule: every session happens exactly once
for s in sessions:
    model.AddExactlyOne(x[s, t, r] for t in allowed_times(s) for r in suitable_rooms(s))

# Rule: a room holds at most one session per period
for r in rooms:
    for period in all_periods:
        model.AddAtMostOne(x[s, t, r] for (s, t) in sessions_covering(period, r))

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
status = solver.Solve(model)   # OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN
```
Our real model (`backend/app/scheduling/solver.py`) is this idea plus the remaining rules and preferences.

---

## 5. When it's impossible: how we explain *why*

A solver that only says "INFEASIBLE" would be useless to a coordinator. We explain at three levels:

| Level | What it does | Example message |
|---|---|---|
| **1. Input checks** (as you type) | Catches obvious mistakes | "Batch strengths (20 + 15) don't add up to class strength 40." |
| **2. Pre-flight checks** (milliseconds, before solving) | Simple counting. If something needs more than exists, it can't work | **"Subject DFIS103 requires 3 weekly periods, but its assigned faculty member Dr. R. Sharma is available for only 2 periods."** ← exactly the PS example |
| **3. Solver diagnosis** (when counting isn't enough) | (a) Ask CP-SAT for the **smallest group of sessions that can't fit together**. (b) Build the best *partial* timetable and, for each session left out, say what blocked it | "These 7 sessions all compete for Dr. Sharma's 6 free periods." / "DFIS152 (B2): every slot was blocked — faculty already teaching DFIS101, DFIS103; students already in DFIS102." |

Every message has a **Fix →** button that opens the right page, for example the faculty availability grid.

---

## 6. Double safety: the independent verifier

We **don't blindly trust** the solver either. A separate piece of code, the **validator**, re-checks every mandatory rule on the final timetable using completely different code from the solver. If the two ever disagreed, the result would be rejected and never shown as a success.

The same validator also:
- checks every **manual drag-and-drop** move instantly ("✕ Dr. Mehta is busy then");
- colours the grid **green/red while dragging**, so the coordinator sees where a session can go;
- is the **final gate before publishing**.

One decider (the solver) plus one independent checker (the validator) is how safety-critical software is usually built.

---

## 7. Why not an LLM (ChatGPT, Gemini, Llama…)?

LLMs are excellent with **language**. Timetabling is a **combinatorial maths** problem with strict rules.

| Question | LLM | CP-SAT |
|---|---|---|
| Will every mandatory rule be satisfied? | ❌ Not guaranteed. LLMs regularly produce clashes on large schedules and say "done" confidently | ✅ Guaranteed by construction |
| Can it **prove** a timetable is impossible? (required by the PS) | ❌ It will usually produce *something* anyway, or guess | ✅ Mathematical proof + explanation |
| Same input → same output? | ❌ Answers vary between runs | ✅ Deterministic (fixed random seed) |
| Handles 300+ sessions × 35 periods × 30 rooms? | ❌ Too big to reason about reliably in a prompt | ✅ Routine; seconds |
| Finds the *best* timetable, not just *a* timetable? | ❌ No notion of optimality | ✅ Optimises preferences, reports how good |
| Works without internet? (our venue Wi-Fi is unreliable) | ❌ Needs the API | ✅ Runs locally |
| Cost per generation | 💰 Paid per token | Free |
| University data privacy | ⚠ Faculty and student data sent to a third party | ✅ Never leaves our server |

**Where an LLM *could* help later (optional, not core):** as a *front door*, not the brain. For example, the coordinator types *"Move Dr. Sharma's Friday classes to Thursday"*. The LLM only converts that sentence into a structured request, and the solver and validator decide whether it's possible. The guarantee stays intact.

**One-liner for judges:** *"Other teams ask an AI to guess a timetable. Ours is computed by an optimisation engine that guarantees every rule, and proves it when a timetable is impossible."*

---

## 8. Why not other "decision" approaches?

We weren't sure which tools "jev" and "laya" refer to (they may be names of tools we don't recognise). The table covers the families of "decision engines" people usually mean, so we can compare against whichever one was intended:

| Approach | Examples | Why not for us |
|---|---|---|
| **Rule engines / decision tables** | Drools, DMN decision models, if-then business rules | They **evaluate** rules ("is this allowed?"), they don't **search** for an arrangement. Good for checking one move, not for building a whole timetable. (Our validator plays this role.) |
| **Machine-learning decision models** | Decision trees, random forests, neural nets | They **predict from past data**. We have no history of "correct timetables" to train on, and predictions don't guarantee rules. |
| **Genetic algorithms / simulated annealing** | Popular in student projects | Random "evolution" of timetables. Often ends with rules still broken, can't prove impossibility, needs a lot of tuning, and gives different results each run. |
| **Greedy / hand-written backtracking** | "Place biggest class first…" | Quick to code; gets stuck on real data; no optimisation. |
| **SMT solvers** | **Z3** (Microsoft) | Exact, like CP-SAT, and can prove impossibility. But Z3 is designed for **verifying software and logic**; it is much slower than CP-SAT on large scheduling and optimisation problems. |
| **Local-search planners** | **Timefold** (formerly OptaPlanner, Java) | Strong for huge problems, but it returns "best found, with *n* rules broken" rather than proving impossibility. It would also push our backend to Java. |
| **Linear programming (MILP)** | PuLP + CBC, Gurobi | Exact, but CBC is much slower on this kind of problem, and Gurobi is expensive commercial software. |
| ✅ **Constraint programming + SAT** | **OR-Tools CP-SAT** | **Exact, fast, free, proves impossibility, optimises preferences, explains conflicts, runs offline. Best fit for university timetabling.** |

---

## 9. How fast is it?

| Size | Typical time |
|---|---|
| PS example (5 sessions) | well under 1 second |
| Our NFSU demo dataset (~6 classes, ~90 sessions) | a few seconds |
| A full department (~300 sessions, 50 faculty, 30 rooms) | target under 30 seconds |

There is always a **time limit** (default 30 s, adjustable by admin). The server can't be overloaded, and the coordinator sees **live progress** while it works.

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **Constraint** | A rule that must never be broken (hard), or should be followed when possible (soft) |
| **Hard constraint** | Mandatory, e.g. no faculty clash |
| **Soft constraint / preference** | Nice-to-have, e.g. preferred morning slots; breaking it costs penalty points |
| **Variable** | Something the solver decides, e.g. "does this session start Tuesday 09:00 in Room 101?" |
| **Feasible** | A timetable that breaks no hard rule exists |
| **Infeasible** | Proven that no such timetable exists |
| **Optimal** | The best possible timetable by the preference score |
| **Objective** | The score the solver tries to minimise (total penalty points) |
| **Propagation** | Ruling out impossible options by reasoning, like Sudoku |
| **Unsat core** | The smallest set of requirements that conflict with each other, used to explain *why* it's impossible |
| **Validator** | Our independent checker that re-verifies every rule |
| **Session** | One lecture period, or one practical block for one batch |

---

## 11. Key takeaways

1. A **constraint solver** is like a super-fast, mistake-free Sudoku solver: we describe the rules, it finds the arrangement.
2. **OR-Tools CP-SAT** is Google's free, award-winning solver, and the right tool for timetabling.
3. It **guarantees** every mandatory rule, **optimises** preferences, and **proves and explains** when a timetable is impossible, which the PS explicitly requires.
4. An **independent validator** double-checks everything and powers instant drag-and-drop checks.
5. **LLMs are the wrong tool** for this core job: no guarantees, no proof of impossibility, internet-dependent, costly, privacy risk. At most, an optional chat-style front door later.

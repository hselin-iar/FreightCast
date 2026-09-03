# AGENTS — Intelligent Freight Forecasting & Chartering (SAIL PS3)

## Session State
CURRENT_STEP:    Post-Deployment Local Feature Development
LAST_COMPLETED:  Build Step 14 — Deployment (Render + Vercel) ✓ VERIFIED
SESSION_STATUS:  ACTIVE
PAUSED_AT:       (none — parity complete and fully verified)

NOTE (Research Parity & Testing Verification):
- Layer 1 (OPEX + DB Seed + 7-Bucket Cost Breakdown): ✓ Verified
- Layer 2 (Sail Value / Net Margin in Strategy & Schemas): ✓ Verified
- Layer 3 (Worst-Incremental Candidate Ranking): ✓ Verified
- Layer 4 (Frontend UI updates): ✓ Verified with Vite build & live browser test
- Regression Pass: All 277 backend unit tests pass with 0 failures.
- Bug Fixes & Stress Tests (TC1–TC5):
  * TC3 Capacity Bug: Removed min(3,...) cap and clamped fallback assignments to vessel capacity. 300kt Dhamra now cleanly solves as 4 Panamax voyages in MILP (60k+80k+80k+80k).
  * Tax Basis Bug: Tax is computed on effective post-discount freight cost; tax/freight ratio is exact 5.0%.
  * Chatbot Scope & Hallucination: Live scope injection + alias normalizer (_normalize_constraints) maps "Cape Max", "Super Max", "Panamax" seamlessly to canonical warehouse classes.
- Comparative Benchmark: All scenarios solve optimally via MILP in ~35ms.
- GitHub Repository: Successfully published and synced to https://github.com/hselin-iar/FreightCast.git (branch main).
- Production Release Commit: `6a3374c` — Includes dynamic recommendation-backed empirical proofs, interactive data term hover inspector, universal LaTeX / KaTeX rendering repairs, and Provenance tab navbar repositioning before Forecast.
- Deployment Configs (Step 14):
  * render.yaml Blueprint: Declares 4 resources (FastAPI Web API, AIS Worker, Retrain Cron, and Postgres DB) with secret keys segregated to server-side only.
  * vercel.json: SPA rewrites configured for React/Vite production build.
  * CORS: Configured in FastAPI to allow all https://*.vercel.app domains.

NOTE (Step 9 verification status): Provenance layer fully implemented and verified.
- provenance.py: Provenance Literal type, tag_measured/tag_modeled/tag_assumed helpers,
  SensitivityBar + SensitivityResult dataclasses, compute_sensitivity() (no re-solve).
- ForecastObject ORM: provenance column added (default="modeled").
- forecasting.py: uses tag_modeled() at write time.
- cost_terms.py: CostBreakdown carries typed Provenance + provenance_note (assumed path).
- decision.py: Strategy carries typed Provenance + provenance_note; fallback Strategies
  also use tag_assumed() with explanatory notes.
- 21 new provenance tests pass. 233 existing tests still pass (no regressions).

NOTE: This project starts with only `freight-optimization/` (the offline handoff
research pipeline — CSV-in/CSV-out, never ported directly, per DOC2 §1) present in the
repo. No `/backend`, `/frontend`, or any Build Step 0–15 work exists yet. The previous
renumbering note (about steps 1–7 having been built under an old step order, and
Provenance needing verification before Step 9) no longer applies and has been removed —
there is no prior work to reconcile. Build steps proceed in DOC4 §4.1's order starting
at Step 0.

---

## Load Order (follow exactly — do not load speculatively)

SESSION START:
  1. Read AGENTS.md fully
  2. Check SESSION_STATUS:
       RESUMING   → go to RESUMING protocol below
       BLOCKED    → re-read the BLOCKED entry, wait for Nilesh
       CHECKPOINT → go to CHECKPOINT protocol below
       ACTIVE     → continue to step 3
  3. Go to DOC4.md → find CURRENT_STEP entry → read only that entry
  4. Follow its DOC2/DOC3 reference pointers → read only the named section, not the whole file
  5. Begin work

NEW STEP:
  1. Update Session State header above
  2. Read the next Build Step entry in DOC4.md §4.1 only
  3. Follow its reference pointers
  4. Begin

WHEN SOMETHING IS UNCLEAR:
  System behavior / walkthrough        → DOC2.md §3 (three walkthroughs), or the numbered
                                          section named in the current step's reference
  Module structure or interface        → DOC3.md, relevant FEATURE section only (see its
                                          INDEX table at the top for the pointer)
  Build order or Done When condition   → DOC4.md, current step entry only (see its Table
                                          of Contents at the top for the pointer)

NEVER load a whole document when a section pointer is available.
NEVER pre-load a later build step before the current one's Done When is satisfied.
NEVER load vibe-antipatterns.md or prompt-patterns.md speculatively — only via Triggers below.

---

## States

### ACTIVE
Working on CURRENT_STEP. Stay here until Done When is satisfied.
  ✓ Work only on the current build step's Folder/file targets
  ✓ Follow the Agentic Coding Rules below at all times
  ✗ Do not touch code outside the current step's scope
  ✗ Do not ask Nilesh questions DOC2/DOC3/DOC4 already answer
  → CHECKPOINT if Done When is satisfied and a checkpoint follows (DOC4 §4.1 inline, or §4.3)
  → BLOCKED if you cannot complete the step without information you don't have
  → ACTIVE (next step) if Done When is satisfied and no checkpoint follows

### CHECKPOINT
Verification gate. Do not continue until it passes.
  1. Read the matching CHECKPOINT entry — Checkpoints A–D sit inline in DOC4.md §4.1,
     right after the build step that triggers them
  2. Run the exact verification described
  3. Report to Nilesh: what you tested, what happened
  4. Wait for confirmation
  → ACTIVE if confirmed pass   → BLOCKED if it fails

### BLOCKED
  1. Set SESSION_STATUS: BLOCKED
  2. State what you were trying to do (one sentence)
  3. State exactly what's blocking you (paste error / quote the ambiguity)
  4. State which doc section you checked and what it said
  5. State what you need from Nilesh
  6. Check Triggers below — follow its pointer if one matches
  7. Wait. Do not attempt workarounds.
  → ACTIVE once Nilesh provides the missing piece and confirms

### RESUMING
  1. Read LAST_COMPLETED → verify its Done When still holds in the codebase. If
     LAST_COMPLETED is blank/none, verify no earlier build step's Done When is
     unexpectedly already satisfied before assuming CURRENT_STEP is genuinely the
     first open step — do not assume a step is covered just because a later one is.
  2. If verified → set CURRENT_STEP to the next step, SESSION_STATUS: ACTIVE
  3. If not verified → tell Nilesh what's incomplete, ask whether to finish or move on
  4. One sentence to Nilesh: what's done, what's next
  5. Never assume prior work is correct — verify before trusting
  → ACTIVE once the prior step is verified

---

## Triggers

When you notice...                                              → Read this immediately

You (or a prior session) write a DB query or SQLAlchemy call
outside /backend/warehouse/repository.py                        → vibe-antipatterns.md AP-06,
                                                                    then prompt-patterns.md PP-07

You fold the MILP variables (q_i,x_iv,y_ip,z_iτ,w_im,ℓ_ip) into
one joint index, or decision.solve() is quietly always returning
"hybrid_fallback" instead of "milp"                              → vibe-antipatterns.md AP-07,
                                                                    then prompt-patterns.md PP-09

You're about to change the signature of decision.solve(),
cost_terms.build_cost_coefficient(), or repository.py's typed
functions to something more convenient right now                → vibe-antipatterns.md AP-09,
                                                                    then prompt-patterns.md PP-08

Anything resembling multi-contract / multi-ship fleet-portfolio
allocation (Step 51V) starts appearing inside decision.py, or a
parameter gestures toward it "for later"                         → vibe-antipatterns.md AP-01,
                                                                    then prompt-patterns.md PP-04

You start Build Step 13 (Dashboard sellable layer) or Step 14
(Chatbot) while Step 12's core form isn't Done yet                → vibe-antipatterns.md AP-01,
                                                                    then prompt-patterns.md PP-04

You're about to report a step "Done ✓" for Decision Engine,
Forecasting, or Cost Terms without having run
test_decision_engine_milp.py / test_cost_terms.py and read
the actual output                                                → vibe-antipatterns.md AP-14,
                                                                    then prompt-patterns.md PP-20

You hit a bug in carried-over code (constraint.py, or the AIS
listener's port-congestion half) or another module outside the
current step, and start fixing it                                → vibe-antipatterns.md AP-13,
                                                                    then prompt-patterns.md PP-12

Session about to end / context filling                           → prompt-patterns.md PP-14
Resuming after any break                                         → prompt-patterns.md PP-02
Agent stuck after 3+ attempts on same problem                    → vibe-antipatterns.md AP-13,
                                                                    then prompt-patterns.md PP-13
Two docs seem to conflict                                        → prompt-patterns.md PP-17

---

## Agentic Coding Rules

ALWAYS:
  - Route all warehouse access through /backend/warehouse/repository.py — no raw SQL or
    SQLAlchemy queries anywhere else in the codebase.
  - Keep MILP decision variables decomposed (q_i, x_iv, y_ip, z_iτ, w_im, ℓ_ip) per DOC2
    §11 — never fold them into one joint index.
  - Reuse cost_terms.build_cost_coefficient() for every MILP objective term in decision.py —
    never hand-roll a cost calculation inline.
  - Set `provenance` on a value at the point it originates (forecasting.py, cost_terms.py,
    congestion.py, decision.py) — never compute it later from the outside.
  - Route every frontend→backend call through /frontend/src/lib/apiClient.ts.

NEVER:
  - Never build any part of Step 51V's batch fleet-portfolio optimizer (multi-contract /
    multi-ship allocation) in this API path, in any form, even partially — it's out of
    scope per DOC2 §13 and DOC4's Decision Engine deferral note.
  - Never make decision.py's variables per-IMO — they stay at the vessel-CLASS level
    (x_iv), even once real AIS position data grounds a τ calculation.
  - Never train or retrain forecasting models inside a FastAPI request path or startup
    hook — only from the scheduled entrypoint (ingestion/scheduler.py).
  - Never let the chatbot bypass /recommendation or compute a number itself — it calls
    the exact same logic the dashboard form uses, no second code path.
  - Never expose ANTHROPIC_API_KEY, DATABASE_URL, AISSTREAM_API_KEY, or
    MYSHIPTRACKING_API_KEY to the React/Vercel build.
  - Never revert to a uniform daily/weekly MILP time grid — event-based τ points are
    load-bearing for keeping the solve inside MILP_SOLVE_TIMEOUT_SECONDS.

IF THE AGENT GOES OFF-TRACK:
  If a feature from a later build step appears while still on an earlier one, say: "Stop.
  We are only doing Build Step [N]. Finish [Done When] before anything else." If
  something resembling Step 51V's fleet-portfolio optimizer appears, say: "Stop — that's
  explicitly deferred, not part of this system." If a design contradicts a decision
  locked in DOC2 or DOC3 §0 (e.g. training at startup, a joint MILP index, a different
  solver/stack), point at the specific decision row and ask why before proceeding.

---

## Quick Reference

DOC2.md               → System architecture: three walkthroughs (§3), data flow (§4),
                         parameter map (§6), MILP formulation (§11), risks (§19).
                         Stack/scope DECISIONS live in DOC3 §0, not DOC2.
DOC3.md                → INDEX table at the top routes to each FEATURE section (module
                         structure), §0 decisions locked, §1 repo layout, §2 constants.py,
                         §4 deployment.
DOC4.md                → Table of Contents at the top. 16 build steps (Step 0–15),
                         Checkpoints A–D inline in §4.1, Agentic Coding Rules (§4.2),
                         Deployment Checklist (§4.4). Current: Build Step 0 — Scaffold /
                         Config.
vibe-antipatterns.md   → Named failure modes with guards (load only via Triggers above)
prompt-patterns.md     → Prompt structures for specific situations (load only via Triggers above)
AGENTS.md          → You are here. Update Session State after every step.

Progress:  DOC4.md §4.1 → CURRENT_STEP entry
Unclear:   Load only the specific doc section that answers it
Stuck:     Set BLOCKED, follow state protocol, check Triggers
Ending:    Update header, note PAUSED_AT, tell Nilesh, stop cleanly

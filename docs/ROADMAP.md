# Delivery roadmap

Each milestone is a small reviewable increment. Update its status and record
verification in `PROJECT_STATE.md`. Packaging quality is continuous work.

| Milestone | Scope | Acceptance gate |
| --- | --- | --- |
| M1 — complete | Repository memory, modular desktop shell, website login, initial packaging | Live login verified; 21 tests pass; packaged GUI/browser smoke passed on GitHub Windows; local EXE launch denied and tracked |
| M2 — individual cow dates implemented, client verification pending | Dynamic farms; cow/From/To rows with folding and shared-date convenience; exact animal lookup; fresh-browser reconnection; one export per cow/period | First live batch succeeded; individual-date GUI-to-browser and 300-row checks pass offline; client confirms per-cow periods, usability, emails and date semantics |
| M3 — implemented compatibility path; paused | User-triggered Microsoft 365 or classic-Outlook newest-N, plus saved-email import; reviewed nested-forward/direct links; validated B3-named downloads; portable folders and same-selection resume | Kept as a legacy fallback while direct API is accepted; Graph deployment and original-mail acceptance remain pending; see EMAIL_COLLECTION.md |
| M4 — direct API implemented; client acceptance pending | Primary API sign-in; spacious multi-path target browser; queue-scoped individual dates and bulk/per-target measurements; responsive reviewed direct JSON/CSV/XLSX collection with raw lineage, compatible staging CSV, tidy graph-ready companion, descriptive workbook overview/index/guide and optional health KPI | Read-only auth/catalog/metrics live check; short-window, queue-selection and workflow regressions plus packaged smoke; client validates representative downloads, date boundaries, units, volumes, both CSV views and workbook usability; see API_DATA.md |
| M5 — automatic single-sheet client table implemented; general master pending | Add per-cow optional T0 to reviewed queue; automatically create one-sheet client-analysis.xlsx in exact 28-column ASPI-style order; use labelled From-midnight period anchor if blank; retain the advanced guided builder and intact audit files | Saved real collection regenerates with seven populated cow rows; exact header/table/style and hundreds-of-cows synthetic tests pass; client confirms actual T0, metric meaning, date coverage and definitions; see CLIENT_STUDY_WORKBOOK.md |
| M6 — study-chart preview implemented; broader analysis pending | Absolute/normal-relative T/A/R cohort Analysis summary plus aligned cow sheets, available n, sample SD and 95% limits from the same derived source | Synthetic chart/reference checks; client validates chart types, offsets, confidence and missing-data handling with real study examples |
| M7 — planned | Anomaly-assisted collection | Agree versioned heuristics and reviewed examples; explain each flag; deduplicate/rate-limit requests; reuse M4–M6; provide review and stop controls |
| M8 — continuous/final gate | Production distribution and support | Signed installer; fresh-machine test without developer tools; usable onboarding; upgrade/uninstall; required notices; clear recovery/help; user acceptance |

## M1 implementation sequence

1. Document the complete product intent and current scope.
2. Establish package structure, dependency locking, developer commands, and CI.
3. Inspect the real login transition without collecting farm data.
4. Implement the browser adapter and a responsive desktop sign-in screen.
5. Cover login states and lifecycle against a synthetic local website.
6. Verify the authorized live login step, stopping at the requested boundary.
7. Build and smoke-test the bundled Windows executable.
8. Update architecture/state/changelog, review for secrets, commit and push.

## Product-wide acceptance criteria

- A nontechnical user can operate installed software without terminal commands.
- Account setup, progress, cancellation, errors and recovery are visible in GUI.
- Correctness and provenance can be checked for every calculation and graph.
- Delays or failures do not silently discard completed work or duplicate requests.
- No credentials, personal session artifacts, or raw farm data enter the repo.
- Future agents can identify current state, boundaries and next steps from files.

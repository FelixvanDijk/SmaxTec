# Delivery roadmap

Each milestone is a small reviewable increment. Update its status and record
verification in `PROJECT_STATE.md`. Packaging quality is continuous work.

| Milestone | Scope | Acceptance gate |
| --- | --- | --- |
| M1 — complete | Repository memory, modular desktop shell, website login, initial packaging | Live login verified; 21 tests pass; packaged GUI/browser smoke passed on GitHub Windows; local EXE launch denied and tracked |
| M2 — individual cow dates implemented, client verification pending | Dynamic farms; cow/From/To rows with folding and shared-date convenience; exact animal lookup; fresh-browser reconnection; one export per cow/period | First live batch succeeded; individual-date GUI-to-browser and 300-row checks pass offline; client confirms per-cow periods, usability, emails and date semantics |
| M3 — design prepared; connector and samples pending | User-triggered newest-N direct/forwarded export email selection; safe downloads; B3 cow naming; portable collection folder | Resolve Outlook/Graph/tenant prerequisites; frozen selection; read-only mailbox; verified links; durable non-overwriting downloads; approved label handling; see EMAIL_COLLECTION.md |
| M4 — planned | Normalization, calculations and master workbook | Agree sample schemas/formulas/layout; preserve raw source and lineage; unit/timezone validation; all requested cows in one workbook; test reviewed expected results |
| M5 — planned | Graphs and analysis | Agree graph specifications; same dataset/config as workbook; readable exportable figures; realistic performance; clear missing/partial data behavior |
| M6 — planned | Anomaly-assisted collection | Agree versioned heuristics and reviewed examples; explain each flag; deduplicate/rate-limit requests; reuse M2–M5; provide review and stop controls |
| M7 — continuous/final gate | Production distribution and support | Signed installer; fresh-machine test without developer tools; usable onboarding; upgrade/uninstall; required notices; clear recovery/help; user acceptance |

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

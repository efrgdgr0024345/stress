# Original plan execution and acceptance ledger

This ledger tracks original requirements, not just successful demonstrations.
The source is `docs/CODEX_MASTER_PLAN.txt` (the supplied 11-page coding plan).
No milestone is complete solely because software tests pass.

## Current user constraints

- Preserve the existing project/drawing-pack website experience. Splitting PDFs
  and scheduling page tasks is a backend implementation detail.
- Prefer the connected private DigitalOcean Functions worker for heavy parsing
  and OCR; bound input/result sizes, memory, execution time, concurrency and cost.
- Continue routine stages automatically. Allow review, editing and explicit
  sign-off while later independent stages run. Never invent missing dimensions
  or sign engineering approvals on behalf of a person.
- Keep original drawings, reviewed edits, revisions and source/catalog hashes.

## Work sequence

- [x] Connect and qualify the private DigitalOcean small-file demonstration.
- [x] Register the newly supplied canonical flange workbook privately on hosting.
- [x] Normalize all four flange data sheets, retain published values/provenance,
  expose source limitations, and prepare reviewable dataset versions.
- [x] Route ordinary project processing through DigitalOcean automatically.
  Split into true single-page source files without changing the website workflow.
- [x] Use scoped, expiring page grants for files beyond the inline function cap;
  fence/cancel/retry tasks and reconcile results to original page identities.
- [x] Expose incremental page evidence and review tasks while processing continues.
- [x] Implement revision-bound staged sign-offs, independent final approval,
  invalidation after edits, and immutable approved issues.
  Releases 0.5.2–0.5.3 passed actual hosting UI/API checks, including a clearly
  synthetic two-account MFA approval, immutable packet and stale element review.
  Real engineering approvals were not performed. Verified modelling stays blocked.
- [ ] Complete typed component ports, node rules, graph/continuation review,
  dimensional constraints and unsupported-feature exception handling.
  Release 0.6.2 adds generic, bounded weld-neck plate/filled-dot recognition:
  13 flange symbols and 26 graphical interface proposals on the real source,
  shown in the drawing inspector and shared website/Excel Source features sheet.
  These are reviewable locations, not accepted physical stations, ordered route
  nodes, material associations or proof of a completed model.
  Release 0.6.0 adds physical interface requirements/mapping and signed XYZ
  constraint solving, source proof, conflict/unknown handling and shared tables.
  General symbol interpretation, automatic continuation proof, arbitrary networks
  and complete physical station/COD proof remain original acceptance gates.
- [ ] Qualify editable PDF layout/objects and complete engineering schedules.
- [ ] Qualify the requested CAESAR import profiles in the actual application.
- [ ] Complete original security, backup/restore and multi-drawing acceptance gates.

## Original milestone acceptance

| Phase | Remaining acceptance evidence |
| --- | --- |
| 0 | Original v1.2 package, its 13 tests and original/golden 1010 assets |
| 1 | General component/interface and network rules plus fixture coverage |
| 2 | Supplied flange workbook now available; valve workbook still missing |
| 3 | Normal live transfers/quotas passed; malware scanning and production storage/security remain |
| 4 | Actual supported desktop-editor save/edit/reopen round trips |
| 5 | Material reconciliation and multiple unrelated drawing fixtures |
| 6 | Signed XYZ chains now implemented; general graph recognition and independent station/COD proof remain |
| 7 | Original 48 unique / 49 display node gates with original assets |
| 8 | Complete native-object layout and editor qualification |
| 9 | Scoped independent review/locked issues passed live software tests; general revision reconciliation and verified-modelling application gates remain |
| 10 | Security, licensing, disaster restore and production operations evidence |

Original requirements stay in scope when unfinished. The later Excel/CAESAR,
cPanel, DigitalOcean, macOS styling and updater requests are separately recorded
in `PLAN_ADDITIONS_FOR_REVIEW.md`.

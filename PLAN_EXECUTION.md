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
- [ ] Implement revision-bound staged sign-offs, independent final approval,
  invalidation after edits, and immutable approved issues.
  Release 0.5.2 implements these controls with disposable API/browser evidence;
  live installation and verification are the next gate. Verified modelling stays
  blocked by the actual export/profile qualification requirements.
- [ ] Complete typed component ports, node rules, graph/continuation review,
  dimensional constraints and unsupported-feature exception handling.
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
| 6 | Reviewed graph, signed XYZ chains and independent station checks |
| 7 | Original 48 unique / 49 display node gates with original assets |
| 8 | Complete native-object layout and editor qualification |
| 9 | New scoped independent review/locked issue implementation needs live validation; general revision reconciliation remains |
| 10 | Security, licensing, disaster restore and production operations evidence |

Original requirements stay in scope when unfinished. The later Excel/CAESAR,
cPanel, DigitalOcean, macOS styling and updater requests are separately recorded
in `PLAN_ADDITIONS_FOR_REVIEW.md`.

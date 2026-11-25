# Bounded closeout plan — 25 November 2026

This is the execution plan for the remaining work in
[the primary request](PRIMARY_1010_REVIEW_2026_11_25.txt). It preserves its
requirements and stage order. It replaces repeated exploratory planning with
four finite checkpoints.

## Starting point

Stages 1–6 are implemented and checked. Stage 7's review packet and documented
CII subset are checked; BEND serialization remains an unmet original requirement,
pending a verified vendor contract. Release **0.8.0 is deployed and live-tested**:
385 tests and both browser mounts passed; the real PDF returned two DigitalOcean
callbacks, and its PDF/XLSX/26 CSV tables were checked from one revision. The
review project is retained. Handoff is recorded in the
[execution ledger](1010_REVIEW_EXECUTION.md) and
[measured live evidence](../LIVE_VALIDATION.md).

The target is a working engineering-review system. Missing source facts are
valid blue exceptions, not software defects to solve by guessing. The five
unlocated CODs, unavailable applicable component weights and missing engineering
approvals must not trigger an endless attempt to manufacture a finished model.

## 1. Finish native PDF output — stage 6

Finish the existing collision planner and existing preview/accept flow; add no
more PDF controls. Use one real-PDF checkpoint to demonstrate all 47 located
points, explicit unlocated/interface warnings, readable schedules and triads,
editable native objects, safe source clearance, and unchanged original streams
and annotations. Acceptance/replanning must retain the same placements.

**Exit:** the focused real-PDF test passes and the PDF code is frozen.

## 2. Finish the export contract — stage 7

Verify the existing website tables, XLSX and CSV against one project revision.
Complete the packet: annotated PDF, workbook, all CSV tables, JSON snapshot,
annotation manifest, exceptions and numbering map/history.

Extend the documented 15.1 CII candidate only to the requested minimum:
straight pipe, bends, tees, rigids and supports/restraints. Complete supported
records may export; missing or unsupported records must block with specific
reasons. Keep actual CAESAR application-import qualification distinct from
software tests. Do not claim an application round trip that was not performed.

**Exit:** review artifacts and supported-component CII tests pass. Record the
unmet BEND contract explicitly; it prevents full native-model completion but
does not prevent delivering the review workflow. Add no export/UI expansion
beyond the primary request.

## 3. Release and prove it live — stage 8

Build one release with compatible rollback safeguards. Run the full suite and
CI after the code is frozen, then deploy through the existing updater. Run the
exact real PDF through the live project and download/reopen the outputs.
Retain that project with its real source evidence and honest blue exceptions.

**Exit:** CI passes apart from the separately documented missing original
golden-assets gate, live results/counts are recorded, and rollback compatibility
is checked. On failure, fix and rerun the affected check; restart the full suite
only when the change warrants it.

## 4. Hand off — stage 9

Record the measured final state, remaining engineering inputs, lessons learned
and a short engineer workflow. Document the fresh-clone reproduction commands.
Keep unsupported/outside-scope ideas in a separate backlog.

**Exit:** the live review project and its exports are usable, the remaining
human decisions are explicit, and the documentation matches the delivered code.

## Cost and scope controls

- Freeze completed stages unless a reproducible failure breaks the required flow.
- One owner per code area; one authoritative real-PDF workflow per checkpoint.
- Reuse the current UI, hosting, updater and worker. Add no infrastructure.
- Run focused checks during changes and one full release qualification.
- Add work only for a failed acceptance criterion or a demonstrated defect.
- A blocked external qualification must be named explicitly; it must not become
  an unbounded rewrite of an otherwise working review system.

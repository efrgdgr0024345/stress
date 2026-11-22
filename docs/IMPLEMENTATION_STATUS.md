# Implementation status — 0.5.0

## Implemented review application

The Python/cPanel pilot is at `https://easyai.com.au/stress/`. The configured
updater installs compatible releases and retains rollback. Check live health
for the installed release; repository state alone does not prove deployment.
Version 0.5.0 adds ordinary-upload DigitalOcean page processing, scoped transfers,
early per-page review in the unchanged project UI, and bounded shared budgets.
The canonical flange workbook is now registered privately and all 627 records
are prepared for human dataset approval. This remains an engineering-review
pilot; original graph/approval/security acceptance gates are still open.
See [execution ledger](../PLAN_EXECUTION.md) and [plan alignment](PLAN_ALIGNMENT.md).

- macOS-inspired React interface and root `loader.php`, with each lesson displayed in a distinct coloured icon card beneath Load project. The Markdown register is version controlled and read dynamically.
- Same-origin, authenticated project loading directly into the in-browser drawing workspace, with project URLs retained across reloads.
- Original PDF pages rendered inside the website. Independent node bubble/anchor editing, explicit model order, main/branch topology, shared point representations, exact engineering units, blue/red reasons and inclusive 152.4 mm support checks.
- Additional native text, rectangle, ellipse and line notes created, edited and removed within the website. Their geometry remains presentation data.
- Materials inventory correction, reconciliation and removal. Specification-bearing changes invalidate previously saved catalog matches.
- XLSX source intake, sheet/header/data-range preview, explicit field mapping/constants, unit conversion and normalization, review errors, versioned immutable dataset approval and strict component matching.
- Per-project catalog row snapshots, workbook and record hashes, approval/match evidence, flange bolting allowances with explicit scope, numeric schedules and N/A for unknown properties.
- Source manufacturer quality is distinct from actual project manufacturer confirmation. A manufacturer's reference record cannot confirm a drawing's manufacturer without explicit vendor/model constraints and evidence.
- Generated PDF preview inside the website and downloadable traceability ZIP. Standard native annotation objects and original content-stream integrity checks; no screenshot-only additions.
- Revision comparison, JSON snapshot download and restoration as a new draft, preserving prior snapshots and exports.
- Server-side tenant/role checks, sessions, optimistic edit conflicts, source hashes, audit events and version-idempotent artifacts.
- Repeatable setup/start scripts, isolated Python environment, npm lockfile, Docker/Compose, CI, API/domain tests and a real Chromium workflow with disposable storage.
- Administrator Logs sidebar with structured request/browser/PDF/update events, filters, request correlation and privacy-conscious diagnostic downloads. See [capture limits](LOGGING.md).
- GitHub release checking, staged code-compatible updates, private backups, failed-health rollback and administrator-triggered rollback. Automatic updates require the account-level cron runner and explicit opt-in.
- The user-provided reviewed 1010 PDF is preserved in GitHub and exercises upload, browser rendering, saved notes and native export in disposable software tests. See [real drawing evidence](REAL_DRAWING_VALIDATION.md).
- Authenticated asynchronous intake, private quarantine, source hashes, durable stage/page checkpoints, leases/fencing, cancellation, retries, expired-lease recovery, duplicate protection and project serialization.
- Native text/vector evidence and Tesseract OCR for outlined/low-text pages, evidence-linked BOM/identity/graph proposals, explicit exact-dimension profile, source exclusions and provisional layout. General recognition remains bounded and unverified facts stay null.
- Separate supervised parser with a tested no-network Docker boundary. Optional Landlock/seccomp fails closed; an explicit resource-limited same-account cPanel pilot mode is available where isolation is unsupported.
- Automatic PDF/XLSX review publication and transactional correction outbox. Cached refresh retains reviewed objects, manual catalog decisions and deletion tombstones; stale/cancelled workers cannot publish artifacts.
- Source revision intake preserving other active documents and unique identical pages across reorder, with changed-page edits archived for reconciliation.
- Excel-style website results with spreadsheet tabs/search, linked drawing/material review, signed element/property editing, native export settings and responsive table scrolling.
- Real editable, numeric XLSX with exact decimal text and literal user strings; CSV tables; gated CAESAR II 15.1 straight-pipe CII candidate based on the vendor's documented contract. Actual CAESAR application qualification is pending.
- Intake authentication before body parsing, body/rate/aggregate job/page limits and active-content rejection. Updates wait for the separate drawing runner before replacing code.

## Deliberate review boundaries

- Engineering acceptance is explicit. Automatic exact station proposals are limited to the documented native semantic profile. General vector/OCR-to-pipe recognition, signed geometry constraints and validated component-specific placement are not complete.
- Main/branch order is explicit, with branches referring to a main-run tee. Arbitrary loops, branch-on-branch networks, signed XYZ constraints and shared namespaces across different lines need richer engineering contracts.
- Shared continuation linking is an explicit user assertion. Automatic candidate finding, per-axis discrepancy calculations and independent continuation approval are pending.
- Source-aware provisional layout avoids extracted exclusions where supported. Wrapping/bounds checks prevent truncated native tables/notes. Complete leader/collision qualification remains open and layout requires review.
- The catalog mapper is general and reviewable, not an assertion that the missing canonical workbooks have been imported. Historical 1010 numeric acceptance gates remain unrun.
- Release remains engineering-review draft. Final engineering approval, verified-for-modelling gates, separate lead/dataset workflows, MFA and external editor qualification are not claimed.
- Standard PDF annotations support broad compatibility. The browser editor is the primary working environment; individual third-party readers may differ in their annotation editing features.
- SQLite/local files are pilot adapters. Scoped remote page transport is implemented in 0.5.0; PostgreSQL/S3, malware scanning, retention/restore drills and full production monitoring remain open. Local bounded registration/splitting is not a separate filesystem sandbox.
- ZIP drawing-pack upload, full native CAESAR component export, independent final approvals and external annotation re-import are not implemented. The first native export profile blocks unsupported components.

## Reference assets

`1010 Reviewed.pdf` has now been supplied and retained at
[`fixtures/1010/`](../fixtures/1010/README.md). Most engineering lettering is
outlined vectors and needs recognition beyond the current text parser. This
reviewed drawing is not the original/golden engineering fixture listed below.

The flange workbook has now been supplied (627 rows in four prepared datasets).
The remaining original reference assets are:

1. `CAESAR_II_Integrated_Generator_v1_2_Valve_Database.zip`, including its original 13 tests.
2. `1010_original.pdf`, authoritative project/annotation blueprints, flange mapping and golden outputs.
3. `Valve_Database_Latest.xlsx`.

Import these immutably when available. Pin hashes, retain their original tests, map the actual source schemas and add the documented numeric, 48-unique/49-display and native-object regressions. Synthetic fixtures must never be presented as real 1010 evidence.

The cPanel pilot was installed through operator-run terminal commands; the cloud
environment was not published by these changes. Keep the pilot access-restricted
while the documented security and operational work remains unfinished.

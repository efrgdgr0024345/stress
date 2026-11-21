# Implementation status — 0.2

## Working local system

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

## Deliberate review boundaries

- Physical dimensions and route definitions are engineer-entered. General OCR/vector-to-pipe recognition, dimension-constraint solving and automatic validated component placement are not implemented.
- Main/branch order is explicit, with branches referring to a main-run tee. Arbitrary loops, branch-on-branch networks, signed XYZ constraints and shared namespaces across different lines need richer engineering contracts.
- Shared continuation linking is an explicit user assertion. Automatic candidate finding, per-axis discrepancy calculations and independent continuation approval are pending.
- Layout is manually reviewed. Wrapping and bounds checks prevent truncated native tables/notes, but there is no complete source-collision solver or guarantee that arbitrary manually placed graphics avoid drawing data.
- The catalog mapper is general and reviewable, not an assertion that the missing canonical workbooks have been imported. Historical 1010 numeric acceptance gates remain unrun.
- Release remains engineering-review draft. Final engineering approval, verified-for-modelling gates, separate lead/dataset workflows, MFA and external editor qualification are not claimed.
- Standard PDF annotations support broad compatibility. The browser editor is the primary working environment; individual third-party readers may differ in their annotation editing features.
- SQLite/local files and synchronous exports are local adapters. Enterprise PostgreSQL/S3/queue infrastructure, isolated workers, malware scanning, rate limits, retention/restore drills and operational monitoring remain production work.
- ZIP drawing upload, proprietary CAESAR model-file export and public deployment are not implemented.

## Required missing reference assets

The plan names files that were not attached or present:

1. `CAESAR_II_Integrated_Generator_v1_2_Valve_Database.zip`, including its original 13 tests.
2. `1010_original.pdf`, reviewed project/annotation blueprints, flange mapping and golden outputs.
3. `PIPE100_Flange_Weights_B16_5_B16_47_API6A_Numbers.xlsx` and `Valve_Database_Latest.xlsx`.

Import these immutably when available. Pin hashes, retain their original tests, map the actual source schemas and add the documented numeric, 48-unique/49-display and native-object regressions. Synthetic fixtures must never be presented as real 1010 evidence.

No public deployment or cloud-environment publication is part of this implementation.

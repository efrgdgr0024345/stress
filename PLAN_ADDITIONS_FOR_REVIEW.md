# Additions outside the original coding-plan scope

Updated 22 November 2026 (Australia/Sydney). The original source remains the
11-page `CAESAR_ISO_Website_Coding_Plan.pdf`, SHA-256
`e2b0ae511754c75de70cd3624faa14f9c4482b7767e7afdea85d44a7fd8faa3d`.

This register separates later user requests and implementation choices from
the starting scope. “Implemented” means a tested software capability, not
engineering approval or a claim that every original milestone is complete.
The user requested that these additions be recorded for later review; this
document does not require another permission step to continue authorized work.

| ID | Addition outside starting scope | Why it was added | Current disposition |
| --- | --- | --- | --- |
| OOS-001 | Unattended upload-to-draft progression and automatic refresh after corrections | Later request to automate the full project pipeline; original plan already required jobs, progress and engineer review, but did not specify fully unattended orchestration | Implemented bounded pilot: durable jobs, leases/fences, stage checkpoints, correction outbox, typed evidence, draft PDF/Excel publication |
| OOS-002 | Existing cPanel/CloudLinux hosting with private SQLite and account cron instead of the proposed PostgreSQL/Redis/S3 production stack | User selected existing hosting and requested low costs/no root/no always-on VM | Implemented pilot adapters. Production infrastructure and cross-host worker deployment remain separate work; no paid DigitalOcean service was created |
| OOS-003 | macOS appearance, loader lessons, system-wide diagnostic export and GitHub updates with rollback | Later explicit user requests | Implemented. Application logs have defined capture/privacy/retention limits; they are not provider OS logs |
| OOS-004 | Formatted Excel-style results as a main deliverable, plus an editable `.xlsx` | Latest explicit user request; original deliverables specified PDF, CSV/JSON and schedules, without this workbook interface | Implemented: browser workbook, engineering element inputs, numeric Excel tables, blank unknowns, exact decimal text, source evidence and readiness gates |
| OOS-005 | Three output types, including a native CAESAR II import candidate | Later explicit request for direct CAESAR use and the top two or three output types; original page 1 excluded a proprietary model exporter unless separately specified and validated | Implemented XLSX, CSV tables and a gated CAESAR II 15.1 straight-pipe `.cii` candidate, using the vendor's documented neutral contract. Required geometry/properties must be entered; unsupported components block native output. Actual CAESAR application import/round-trip qualification and full component profiles remain open. XLSX is not labelled a native CAESAR model |
| OOS-006 | A versioned explicit-point native-text profile for a complete automatic regression | Needed to test all stages independently of unavailable legacy assets and unqualified general recognition | Implemented as a clearly labelled synthetic profile. Literal POINT/ROUTE/ORDER/STATION and DIM statements can produce exact **proposals**. They do not make automatically accepted engineering stations |
| OOS-007 | Unique identical content streams as the initial proof for retaining page identity across reordered revisions | Original revision/stable-ID requirements needed a concrete first matching policy | Implemented. Changed/ambiguous pages archive prior edits for reconciliation; arbitrary geometric/entity rebasing is not claimed |
| OOS-008 | Concrete pilot limits and fail-closed worker capability behavior | Original security requirements specified quotas/isolation but not numeric defaults or hosting failure behavior | Current defaults: 30 MiB per PDF, 100 pages per file, 200 active project pages, 10 pending jobs/project, 100 pending jobs/workspace, 500 logical jobs/day/workspace, 500 MiB automatic input allowance, 64 MiB active extraction evidence, 20,000 workbook data rows. Review these operating limits before expanding the pilot |
| OOS-009 | Local Docker isolation, optional Linux Landlock/seccomp, and an explicitly selected bounded same-account fallback | Make isolation requirements concrete while retaining a practical no-root hosting pilot | Docker adapter tested with networking disabled, read-only root, dropped capabilities and bounded CPU/memory. Landlock depends on host support and fails closed when unavailable. Bounded mode is explicitly **not** a separate filesystem sandbox |

The original requirements for no scaled physical dimensions, component-specific
node rules, independent approval, canonical dataset regression, tenant isolation,
backup restoration, licensing and native-object QA are **not new scope**. They
must not be relabelled as optional additions when unfinished.

OOS-010: The shared-hosting adapter now optionally installs a hash-pinned binary
OCR runtime in account-private storage through the separate runner (0.4.3).
This deployment choice extends the original infrastructure scope; OCR itself
remains an original-plan requirement. It requires no paid service or root and
does not relax the selected isolation mode. See processing setup for platforms,
licenses, failure behavior and the explicit re-extraction action.

See [original-plan alignment](docs/PLAN_ALIGNMENT.md),
[working pipeline/setup](docs/PROCESSING_PIPELINE.md) and
[Excel output contract](docs/EXCEL_OUTPUT.md).

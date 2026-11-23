# Original 1010 acceptance — blocked on source assets

The user's 23 November 2026 instructions supersede the previous feature order:
restore the original golden regression first; then engineering core, native
export, PDF QA, and only then more recognition or production infrastructure.
This restoration checkpoint added no OCR, styling or hosting infrastructure.
The later instruction to proceed with all steps continues independent
engineering-core work in 0.7.0 while retaining this blocked golden gate;
see ENGINEERING_CORE_07.md. It does not replace the missing originals.
The exact [pasted priority instructions](PRIORITY_2026_11_23.txt) are preserved
with SHA-256 `153f23cd3975d21f3aa64a9c8fd1c4c800d1e8edcced59aa04319e980466a052`.

| Immediate requested task | Current result |
| --- | --- |
| Inventory original assets and expected hashes | Complete inventory; seven required asset roles missing; expected hashes unknown |
| Restore original thirteen tests and enforce golden gates | Original suite blocked on ZIP; thirteen new acceptance checks added and deliberately failing |
| Component-node rule tests | Explicit-rule boundary and historic support regressions pass; automatic placement/continuation/COD remain open |
| Exact CII checklist and next three component milestones | Documented; desktop application qualification remains false |

## Immutable source inventory

The working tree, local Git history, current GitHub main and uploaded attachment
names were searched. The following originals have not been supplied. **None of
their trusted expected SHA-256 values is known.** Null means unknown, not a hash
to be calculated from an arbitrary replacement.

| Original asset | Availability | Expected SHA-256 |
| --- | --- | --- |
| `CAESAR_II_Integrated_Generator_v1_2_Valve_Database.zip` | Missing, including original 13 tests | Not supplied |
| `1010_original.pdf` | Missing | Not supplied |
| `1010_review_project.json` | Missing | Not supplied |
| `1010_annotation_blueprint.json` | Missing | Not supplied |
| `1010_flange_specs.json` | Missing | Not supplied |
| Original golden output PDF(s) | Missing; authoritative filenames/layout also unknown | Not supplied |
| `Valve_Database_Latest.xlsx` | Missing | Not supplied |

The available `1010 Reviewed.pdf` has SHA-256
`7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59`.
It is a separate real-source software fixture. Renaming it to the missing
original filename fails the gate. The supplied PIPE100 flange workbook does not
replace the missing canonical valve workbook or original flange-spec mapping.

`fixtures/1010/golden-manifest.json` reserves every required role. Populate its
filename, externally confirmed SHA-256 and trust/source description only after
receiving the authentic assets. Preserve their bytes and names; never overwrite
an existing pinned original. Validate candidate input hashes before importing.
Additional golden PDFs must be individually pinned once their layout is known;
do not merge or manufacture a supposedly original output to fit this placeholder.

Run the read-only inventory:

```sh
python scripts/audit_1010_golden.py --strict --report .local/1010-asset-audit.json
```

It exits 1 while any file, trusted pin or hash-source description is missing or
incorrect. It never downloads, modifies, executes or self-approves an asset.
Matching trusted pins establishes file availability, not engineering validity.

## Original tests and the thirteen NEW acceptance checks

`acceptance/1010/test_golden.py` contains thirteen new checks derived from the
plan. **They are not ports or recreations of the unavailable original tests.**
The separate `Original 1010 acceptance (required evidence)` CI workflow is
deliberately red while required evidence is absent; ordinary software regression
tests remain separate. No missing gate is silently skipped or marked complete.

The original archive must be inspected before restoring its source, dependencies
and actual thirteen tests under `legacy/1010/`. Its reviewed runner must execute
the real suite in isolation, with no network or credentials and a disposable
writable directory. The reserved runner contract is
`python legacy/1010/run_original_tests.py --isolated --json`; its JSON reports
`tests_run`, thirteen unique `test_ids`, zero `failures/errors/skipped`,
`archive_sha256` and `isolated: true`. The gate invokes the runner; it does not
accept a hand-written pass receipt. **This runner is not implemented because
the original code/test layout is unavailable.**

The current application's actual candidate artifacts belong in
`.local/1010-golden/`: `project.json`, `review.pdf`, and the native exporter’s
`annotation-manifest.json`. They must be generated from the pinned original
source and reviewed legacy adapters, not constructed to hit the target counts.
The workflow does not currently generate those artifacts; restoring the actual
legacy schemas and adapter is part of blocked Phase A.

`reviewed-oracle.json` is a derived adapter result, not a replacement original:
it records `source_sha256` for every pinned role and the normalized reviewed
`project`. The adapter must be reviewed against the actual legacy JSON schemas
before implementing it. No guessed original schema or engineering oracle exists.

The checks enforce original availability/execution, two sheets on one full line,
48 unique points, 49 instances, one shared Node 170, main 10–370, branches
400–430/500–530/600–620, specific material quantities, accepted station/colour
agreement with the reviewed oracle, current physical interface proof, unchanged
source streams, 297 native additions and named manifest entries. This is a
baseline gate; full weights, editor collision/round-trip and all Phase B–D
requirements remain separate open acceptance work. Any legitimate annotation
count change requires an explicit reviewed baseline change with evidence.

## Engineering rule coverage and remaining work

The labelled synthetic cases in `test_component_plan_contract.py`, existing
`test_physical_model.py` and API tests cover separate flange face/dot proof,
shared valve/inline interfaces, single-ended PIT, common main-run tee identity,
required elbow COD convention, coincident support associations, unresolved
requirements and continuation identity/number preservation. The historic support
gaps (2 inches, 0.5 inches, 2⅛ inches) flag only the downstream same-route
support using accepted along-route stations; nearby PDF coordinates do not merge
points. Renumbering retains IDs, stations, source evidence and colour reasons.

These prove existing explicit-rule behavior. They do not implement automatic
continuation search/axis deltas, automatic tee intersection placement, elbow COD
inference, a full mixed-coordinate dimension recognizer or a production model.
Those original tasks remain blocked behind the source fixture and require new
algorithm tests when Phase B begins. No conditional expected-failure decorators
are used to make missing engineering work appear green.

The exact current native checklist and the next three component milestones are
in [CII readiness checklist](CII_READINESS_CHECKLIST.md). Phase A remains **BLOCKED** until
the originals, trusted hashes, original suite and actual golden output gates pass.

Local verification of this checkpoint: **218 ordinary software tests passed**,
including 42 targeted foundation checks. The thirteen separate new original-plan
checks all fail at the missing-original-assets prerequisite, as intended.
This is blocked acceptance evidence, not thirteen executed legacy failures or
an engineering approval. The existing live application release is still 0.6.2;
this checkpoint adds repository tests, evidence requirements and documentation.

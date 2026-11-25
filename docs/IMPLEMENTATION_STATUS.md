# Implementation status — current source tree

This describes the implemented review workflow and completed focused local
proofs. It does **not** assert that a new release is installed or live testing
has finished. [LIVE_VALIDATION.md](../LIVE_VALIDATION.md) records the actual
hosting release, dates and measurements; older live counts must not be replaced
by local source-tree results. See [How an engineer finishes 1010](HOW_TO_FINISH_1010.md)
for the current UI sequence.

## Reviewed 1010 scope

The exact two-page [1010 Reviewed.pdf](../fixtures/1010/README.md) has SHA-256
`7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59`.

| Capability | Implemented behaviour and bounded proof |
| --- | --- |
| Source interfaces | 47 provisional source points, 60 required interfaces, 55 proposed mappings and five explicitly unlocated theoretical CODs. Source inspection, classification and engineering acceptance are separate. |
| Continuations | Four curated source references, reversible reject/external-boundary/reopen decisions, independent signed XYZ comparisons and explicit exact-identity acceptance. Every shared depiction and retired alias is retained; changed source evidence invalidates reviews. |
| Dimensions and stations | Explicit signed XYZ/COD constraints and separate along-route station constraints. Real printed gap proposals retain units, unsigned direction and source witnesses; no pixels or Euclidean distance supply stations. Unknown geometry stays null and blue. |
| Graph and numbering | Source inspection precedes explicit line/route/order/takeoff decisions. Preview/hash-bound atomic apply; main 10/+10, branches next hundred, new lines next thousand. Unassigned points are retained; numbering history preserves physical UUIDs and evidence. |
| Catalogs | Exact user-provided 627-row workbook retained under fixtures/catalogs. Six classified source rows cover 18 flange/valve occurrences; available data leaves all six technical schedules N/A. PV remains a separate unproved classification, not a fabricated valve. |
| Manufacturer | Independent source-bound project confirmation/reopen/history. Catalog quality or dataset approval never confirms the installed manufacturer. |
| Native PDF | Whole-project server-PDF preview and explicit graphical-only acceptance, protected source dimensions/materials/NORTH, native individual labels/bubbles/leaders, axis/moment objects, schedules and blue warnings. The focused 47-point case produced 285 additions. Every object was edited/reopened twice with original raw/decoded streams and original annotations preserved. |
| Review exports | Shared website/XLSX/CSV tables, numeric cells with blank unknowns, source/evidence links, exceptions and histories. Revision packets include the native PDF/manifest, snapshot, numbering map and component/readiness reports; CII is conditional. |
| Native component data | Explicit DRAFT/REVIEWED entries for rigid, tee, restraint and bend inputs. Actual 1010 browser proof saves missing BEND data as null and retains the blocked native download. |

These focused proofs use disposable projects. Real source observations are not
an engineered golden model. Software-only positive topology/CII fixtures are
labelled separately and do not insert engineering facts into the live drawing.
Final combined regression and hosted validation are separate release gates.

## Native CII: implemented subset and unmet requirement

The profile is `caesar-15.1-reviewed-components-v1`. Complete documented straight
pipe, rigid valve/flange records, bounded B31J welding tees and basic grounded
translational restraints can produce import candidates. All supporting source,
station, topology, signed-vector, property and component gates remain strict.
Unknown weight, gap, stiffness, geometry or manufacturer data is not zero.

**BEND generation remains an unmet original requirement.** The verified 15.1
native field-layout and theoretical-COD/native-node geometry contracts are
missing/ambiguous. No point mapping, radius entry, note or checkbox bypasses the
block. [CII_151_COMPONENT_CONTRACT.md](CII_151_COMPONENT_CONTRACT.md) records the
bounded contract and unresolved bend questions.

The actual 1010 drawing still lacks accepted engineering geometry, routes,
stations, complete component data and manufacturer evidence; its CII remains
blocked. A real CAESAR II application import/round trip and stress analysis have
not been performed. `qualified_application_roundtrip` remains false. Native
serialization tests are not proprietary-application qualification.

## Existing application and operating boundaries

The website retains the macOS-style loader and GitHub lessons register,
authenticated in-browser drawings, materials/source editing, durable extraction
jobs, DigitalOcean page processing, audit/log downloads, revision history,
review controls, updater/rollback and recoverable scoped workspace reset. Page
splitting is a backend processing detail; the website keeps the project/drawing
pack experience. Prefer the existing bounded serverless processing path rather
than adding an always-on VPS for these jobs.

Independent review controls do not automatically approve the real drawing.
Outputs remain engineering review drafts until an applicable explicit review
issue is completed. Verified-for-modelling qualification, stress analysis and
universal desktop-PDF-editor compatibility are not claimed. SQLite/private
files and bounded same-account cPanel processing remain pilot arrangements;
local resource limits are not a separate filesystem sandbox. Production
security, backup/restore and deployment boundaries remain documented in the
hosting/security guides.

## Separate original/golden regression gate

The reviewed PDF and supplied flange workbook are available. These original
reference assets remain absent:

1. `CAESAR_II_Integrated_Generator_v1_2_Valve_Database.zip`, including its original 13 tests.
2. `1010_original.pdf`, authoritative engineering/annotation blueprints, flange mapping and golden outputs.
3. `Valve_Database_Latest.xlsx`.

Their historical numeric and 48-unique/49-display regressions remain unrun. Keep
that gate explicit; do not force these counts onto the reviewed drawing or stop
its source-review workflow waiting for missing assets. Import future assets
immutably with pinned hashes, without substituting synthetic fixtures.

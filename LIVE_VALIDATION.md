# Live demo validation and clean workspace

Verified on **23 November 2026, Australia/Sydney**. Installed release: **0.6.2**.
The live site is https://easyai.com.au/stress/.

The newest user attachment is byte-for-byte the retained
`fixtures/1010/1010 Reviewed.pdf`, SHA256
`7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59`.
It was uploaded again through the ordinary live project intake. Both pages
processed through DigitalOcean and returned by authenticated page callbacks.
The original download and every original PDF content stream remained unchanged.
Actual rendered drawing/preview pixels, website tables, downloaded numeric XLSX,
CSV tables and the native PDF review bundle passed live checks.

| Real drawing result | Observed |
| --- | --- |
| Drawing pages | 2 |
| Material proposals | 32 |
| Graphical flange-symbol proposals | 13 (4 on sheet 1, 9 on sheet 2) |
| Separate proposed face / pipe-dot locations | 26 |
| Component occurrences prepared | 37 |
| Required physical interfaces | 56, unlocated |
| Physical node proposals | 0 |
| Engineering/model verification | Incomplete |

The new bounded vector recognizer requires a thin plate, a separate filled dot
and collinear heavy linework. It uses drawing geometry rather than a stored
1010 location/count map. **Detected features** shows blue face/dot locations in
the drawing inspector; **Source features** shares the same 26 rows between the
website and exported Excel workbook. Graphic X/Y values are explicitly PDF
points; unknown physical stations remain blank.

The actual live browser saved two clearly unverified test points from one face
and its separate pipe dot, reselected the saved point without duplicating it,
switched sheets, rendered actual PDF pixels and downloaded/reopened the numeric
workbook. No engineering stations or material associations were approved.
Both source pages returned through private DigitalOcean callbacks; the live
worker ZIP exactly matched the locally qualified package (about 300 MB peak
parser memory and 6–9 seconds of handler time per page). Browser errors: zero.

This is a working **engineering-review demo**. General automatic physical-point
placement, station/COD/continuation inference and fully verified CAESAR modelling
remain unfinished. The new graphic proposals do not resolve those 56 physical
interface requirements. Requirements and unknowns are visible in the
website/Excel sheets; no station or point location was fabricated. The original
plan's missing legacy/golden assets, canonical valve workbook, actual desktop
round trips and production security/operations qualification remain in scope.
See [execution ledger](PLAN_EXECUTION.md) and [physical model](docs/PHYSICAL_MODEL.md).

Separate clearly labelled synthetic tests passed source-bound shared-interface
mapping, signed XYZ entry/acceptance, workbook reopening, independent two-account
MFA review approval, sealed packet integrity and review invalidation after edits.
These are software tests and do not approve the real drawing. The local suite
passed 205 tests. Final source-binding API checks, extracted WSGI package checks,
19 bootstrap/routing tests and the final browser feature workflow also passed.
GitHub validation and serverless qualification passed:
https://github.com/efrgdgr0024345/stress/actions/runs/45092478840/job/137424919991.

The earlier 0.6.1 reset archived and cleared 10 projects,
10 original source files, 6 exports, 1 synthetic approved issue, 7 processing runs,
2 temporary accounts and 1 provider demonstration. A private database/files
backup was created before removal. The live browser now shows an empty project
workspace and an enabled New project action. After the new 0.6.2 live test,
the single additional test project and its files/exports were privately backed
up and cleared again. The live projects API confirms an empty workspace.

The genuine administrator/session, all four prepared flange datasets (627 rows),
DigitalOcean connection/ready normal processor, automatic updates and paid-use
counters were retained. The canonical workbook preview was reopened after reset.
No paid always-on VPS or extra managed database/storage was added.

Machine-readable proof, including the explicit incomplete-engineering status:
[0.6.2 live validation](serverless/digitalocean/evidence/flange-location-live-validation.json),
[qualified function package](serverless/digitalocean/evidence/flange-location-qualification.json)
and [earlier 0.6.1 validation](serverless/digitalocean/evidence/final-live-validation.json).

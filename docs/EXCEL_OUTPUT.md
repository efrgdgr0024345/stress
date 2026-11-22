# Excel results and the CAESAR import boundary

**Excel results** is the main formatted tabular output in the website. It has
sheet tabs, frozen headings/row indexes, filters, numeric alignment, explicit
unknowns and green Excel export controls in the website's macOS visual style.
Select a node to review it on the drawing, or an element row to enter signed
geometry, pipe properties, material code, temperature, pressure and evidence.

Every new review bundle contains a real editable `.xlsx`, also downloadable on
its own. The generated file is reopened before publication. It has no macros,
external links or formulas created from user/drawing text. Unknown numeric
values are blank; they are never replaced with zero. Excel stores numbers with
finite precision, so a separate **Exact values** sheet retains canonical decimal
strings without rounding away engineering evidence.

| Sheet | Content |
| --- | --- |
| Read me | Revision, units, review status and use limitations |
| Nodes | Stable IDs, numbers, line/route/type, accepted stations, separately labelled source station proposals, evidence and reason codes |
| CAESAR input | From/to numbers, signed XYZ deltas, separate route distance, OD/wall/corrosion, material code, temperature/pressure, evidence and element IDs |
| Supports | Accepted stations, support gaps and reasons; no distances from graphics |
| Components | Inventory/raw source quantities, located counts, catalog values, weight scope and project manufacturer/match quality |
| Exceptions | Unresolved source/engineering/layout issues |
| Sources | Original source hashes, page identity and registry data |
| Exact values | Canonical decimal text corresponding to numeric fields |
| CAESAR readiness | Server-evaluated completion gates and outstanding qualification |

The workbook schema is `caesar-engineering-workbook-1`. This is a working Excel
file and an engineering data handoff, **not a claim that arbitrary `.xlsx` files
are accepted by CAESAR II**. Direct import is the user's new expanded requirement
(OOS-005). It needs the actual CAESAR II version, supported import method/template,
field/unit/code mappings and a successful round trip in that application.
Those details have been requested; no proprietary/neutral format is guessed.

Before an import-ready claim, qualify at least: all active elements represented;
correct signed deltas/units; actual pipe OD/wall/material and load properties;
restraints/rigids/branches/interfaces as required by the chosen format; source
exceptions and reference-only component values resolved; engineering approval;
and model counts/coordinates/properties checked after CAESAR import. Model
geometry cannot be manufactured from the isometric's appearance to make a file
pass an import parser.

The web/API protects current project revisions. Changing cells in a downloaded
workbook does not silently overwrite website data or run software on a Windows
or Mac computer. An import connector/round-trip edit contract requires its own
qualified mapping; the exported file contains no executable installer or macro.

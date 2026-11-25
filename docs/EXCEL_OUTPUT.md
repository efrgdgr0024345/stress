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
are accepted by CAESAR II**. The user selected two or three useful output types:
the website provides this workbook, UTF-8 CSV tables in a ZIP, and a gated native
CAESAR II 15.1 `.cii` import candidate. See [formats and vendor sources](CAESAR_FORMATS.md).
The current bounded native profile supports complete explicit straight-pipe,
rigid valve/flange, B31J welding-tee and basic translational-restraint inputs.
BEND generation remains an unmet requirement with a named external contract
blocker. No actual CAESAR application round trip is claimed.

Additional shared tabs expose component ports, dimensions, printed coordinates,
station constraints/datums, graph edges, numbering history, catalog schedules,
per-occurrence N/A data, independent manufacturer reviews and native component
requirements/inputs. Every CSV table is included in the review packet at the
same project revision. Native input drafts keep their original entered text;
only finite, in-range values populate their numeric draft cells.

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

In the website, **Nodes**, **CAESAR input**, **Supports**, **Components**,
**Exceptions** and **Sources** are live views of the same server-side table
projection used for XLSX/CSV. Element rows open an evidence-backed editor;
**CAESAR export settings** records the code ID, ambient temperature, vertical
axis and explicitly acknowledged local origin. Native export remains disabled
while required inputs/components are unresolved. Wide tables scroll inside
their panel on small screens. Unknown counts and pipe lengths are separate:
44.9 m of pipe must not become 44 or 45 component instances.

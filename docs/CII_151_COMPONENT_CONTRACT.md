# CAESAR II 15.1 component neutral contract

This is a transcription of the official **15.1** format, retrieved 25 November
2026. The publication identifies its last edition as 17 November 2026. It is a
serialization contract, not approval of engineering inputs or proof that an
application import succeeded. No CAESAR II application round trip has been run.

Official sources:

- [Control counts](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337039)
- [Basic elements and auxiliary pointers](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337040)
- [Auxiliary records](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337041)
- [Unit conversions and labels](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337060)

Numeric records use `(2X,6G13.6)`. The vendor also permits
`(2X,6(1p,E13.6))` for seven significant digits. Integer records use
`(2X,6I13)`: two leading spaces followed by fields of width 13. These are
version-specific records; changing the version label does not qualify another
version.

## Counts and linkage

The first CONTROL record contains, in order: element, nozzle, spring-hanger,
node-name, reducer and flange counts. Its next 13 integers are:

`BEND, RIGID, EXPJT, RESTRANT, DISPLMNT, FORCMNT, UNIFORM, WIND, OFFSETS,
ALLOWBLS, SIF&TEES, IZUP, EQUIPMNT`.

`IZUP` is 0 for Y vertical or 1 for Z vertical. Counts refer to auxiliary
**blocks**, not component ports or physical points. Each basic element has 15
used IEL pointers, in this order:

`BEND, RIGID, EXPJT, RESTRANT, DISPLMNT, FORCMNT, UNIFORM, WIND, OFFSETS,
ALLOWBLS, SIF&TEES, NODENAME, REDUCERS, FLANGES, EQUIPMNT`.

A pointer selects the corresponding 1-based auxiliary block; 0 means absent.
For example, BEND uses IEL 1, RIGID 2, RESTRANT 4 and SIF&TEES 11. Auxiliary
sections retain the documented order even when empty; an empty section has its
header only. NODENAME is optional and precedes BEND.

[Code and Edition](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/1528364),
linked from ALLOWBLS' piping-code field, explicitly maps code **editions** to
numeric IDs. The relevant subset is:

| Code family | Edition → native ID | Default B31J edition |
| --- | --- | --- |
| B31.3 | 2018 → 3 | Not specified in this table (`--`) |
| B31.3 | 2020 → 43; 2022 → 53 | B31J-2017 |
| B31.3 | 2024 → 63 | B31J-2023 |
| B31.1 | 1967 → 20; 2018 → 1 | Not specified in this table (`--`) |
| B31.1 | 2020 → 42; 2022 → 52 | B31J-2017 |
| B31.1 | 2024 → 65 | B31J-2023 |

Thus numeric ID 3 must not be described as B31.3-2024 or assumed to enable a
particular B31J edition. Lock and review the supported code/edition/settings;
other code IDs require their own verified mapping and field semantics.

## BEND: documented inconsistency remains a blocker

The official auxiliary page declares `BND(N3,15)` and says, **“Only 13 items
are currently used”**, written on three numeric lines. Its numbered list
actually contains **14** entries:

| Position | Field |
| --- | --- |
| 1 | Bend radius |
| 2 | Bend type: welded 0/blank, single flange 1, double flange 2 |
| 3–4 | Angle to position 1; node number at position 1 |
| 5–6 | Angle to position 2; node number at position 2 |
| 7–8 | Angle to position 3; node number at position 3 |
| 9 | Number of miter cuts |
| 10 | Fitting thickness, when different from pipe |
| 11 | Seam weld: yes 1, no 0 |
| 12 | Bend flexibility K factor |
| 13 | Weld strength reduction factor WL |
| 14 | Overlay thickness |

Do not silently choose 13/14/15 values, invent slot 15 semantics or claim this
ambiguity is resolved. A matching 15.1 application export or vendor clarification
is needed. Bend type also has different meanings for FRP codes; the metallic
interpretation above is not universal.

[Angle 1, 2, 3](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/335014)
states: **“The element To node is always physically located at the far end of
the bend.”** The software can create start/midpoint curvature nodes by default.
[Node 1, 2, 3](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/335015)
requires unique additional node numbers. A source theoretical COD must not be
silently reinterpreted as a native bend end, tangent or curvature node. The
representation, tangent connectivity, radius, angles and node mapping need
explicit evidence and application verification. Drawing pixels supply none of
these physical values.

## RIGID

`RIG(N3,2)` has one numeric line: **rigid weight, rigid type**.
[Rigid Type](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/927165)
defines 0 unspecified, 1 valve, 2 flange, 3 flange pair and 4 flanged valve.

[Rigid Weight](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/335041)
is force, typically lb or N, and excludes fluid and insulation. Blank/zero
creates a weightless construction element and suppresses added fluid/insulation
weight. An unknown real component weight must therefore block export instead
of becoming zero. Catalog scope and manufacturer confirmation remain separate
review requirements.

## RESTRANT

`RES(N2,102)` uses **24 lines per block**: six slots, each with four lines.
For each slot the first two numeric lines contain, in order:

`node, type, stiffness, gap, friction coefficient, connecting node,
X cosine, Y cosine, Z cosine`.

The first line holds six values and the second the remaining three. The next
two lines are support tag and support GUID, each `(7X,I5,1X,A100)`. The integer
prefix is string length; a blank string has length 0. Node fields contain native
node numbers, not UUIDs or auxiliary indexes. Occupied restraint types are 1–62.

The official auxiliary page's type table begins: 1 ANC, 2 X, 3 Y, 4 Z, 5 RX,
6 RY, 7 RZ, 8 GUI, 9 LIM. Do not infer any of these from a drawing support tag.
[Restraint Type](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/335364)
and [Gap](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/335382)
describe type-specific overloads: rods, bilinear restraints, springs and snubbers
do not share ordinary gap/friction semantics. A narrow writer must reject types
whose full field meaning it does not support.

## SIF&TEES

`SIF(N4,84)` contains **two 42-value node slots**: seven numeric lines each,
14 lines per block. The order within each slot is:

| Positions | Fields in order |
| --- | --- |
| 1–6 | Intersection node; type; in-plane SIF; out-of-plane SIF; weld mismatch; fillet leg |
| 7–12 | Pad thickness; fitting outside radius; crotch radius; weld ID; B1; B2 |
| 13–18 | In-plane index; out-of-plane index; axial SIF; torsion SIF; pressure SIF; pressure index |
| 19–22 | Not used |
| 23–24 | Code-related checkbox options |
| 25–30 | Axial index; torsion index; surface node (B31J); three unused B31J fields |
| 31–36 | Number of flanges; maximum mismatch; reinforcement type; radius r2; reinforcement thickness tn; reinforcement length L1 |
| 37–42 | Angle theta_n; taper large end y; effective branch thickness; three unused B31J fields |

The second slot repeats this order. The page permits 0.0 for unused values, but
fields **23/24 explicitly use 1 selected, 0 cleared, 9999.99 unspecified**.
Required unknown engineering inputs must still block; unused slots and
documented sentinels are different from missing required inputs.

[Tee Type](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/346179)
is code-dependent. For B31J, 1–6 are reinforced, fabricated, welding, Sweepolet,
Weldolet and extruded tees. An omitted type supplies SIFs only and does not
establish a tee. Proper classification is necessary for local tee-axis SIF
application. Use the existing reviewed intersection identity and native number;
do not create a separate branch tee to satisfy the record.

## Units and qualification

The existing writer declares English units. Lengths are inches, force is lbf,
angles are degrees, translational stiffness is lbf/in and rotational stiffness
is in·lbf/degree. K, WL, SIFs, indexes, friction and direction cosines are
dimensionless where the selected piping code defines them that way. Other
code-specific fields require their own documented meaning.

- mm → in: divide by 25.4.
- N → lbf: divide by 4.4482216152605.
- N/mm → lbf/in: multiply by 25.4 / 4.4482216152605.
- N·mm/degree → in·lbf/degree: divide by (25.4 × 4.4482216152605).

Structural tests can check widths, counts, field positions, conversions and
pointer targets using clearly labelled software-only vectors. They cannot
qualify CAESAR application behavior. Qualification still requires a licensed
15.1 converter/application round trip, retained diagnostics and comparison of
geometry, generated bend nodes, properties, auxiliaries and numbering against
the source-bound manifest/workbook. Until then retain
`qualified_application_roundtrip: false` and `IMPORT_CANDIDATE_ONLY`.

The actual 1010 drawing's unresolved CODs, classification, geometry, stations,
weights or restraint definitions remain blockers. They must not be filled from
test vectors, software defaults or drawing pixels.

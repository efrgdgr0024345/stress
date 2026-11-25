# How an engineer finishes the reviewed 1010 drawing

This guide follows the current website controls. It describes the source tree,
not a claim that a new release has reached the hosting account. Check
[LIVE_VALIDATION.md](../LIVE_VALIDATION.md) for the installed release and observed
live results. All outputs remain **engineering review drafts** until the
appropriate independent approval has actually been completed.

Use the exact [1010 Reviewed.pdf](../fixtures/1010/1010%20Reviewed.pdf), SHA-256
`7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59`.
It contains two sheets. Source preparation supplies **47 provisional source
points and 60 required component interfaces**: 55 proposed mappings and five
unlocated theoretical elbow COD requirements. These are review observations,
not 47 proved engineering nodes or a complete physical model.

## 1. Establish the source and inspect its interfaces

Upload the drawing or open its project. Keep the full line identity and inspect
both sheets in **Drawing workspace**. In **Drawing register**, confirm the
printed sheet identities and full line IDs from the actual drawing.

In **Excel results**, choose **Locate source interfaces**. Inspect the source
feature and anchor of each required point in Drawing workspace before checking
**Confirm current source feature and visual anchor**. Inspect every depiction
of a shared point separately. Source inspection does not accept route order,
station, XYZ, manufacturer or an engineering issue.

Use the component-port controls and **Review source exceptions** to reconcile:

- Flange face and opposite centreline black-dot interfaces; adjacent process ends share only a proved common interface.
- One tee point at the main/branch intersection, belonging to the main series.
- Distinct support stations; merge only on proved coincidence.
- Two process ends for inline items and one for a proved single-ended instrument.
- Five theoretical elbow CODs, which need accepted leg/dimension evidence. A nearby printed angle or drawing pixel is insufficient.

PV-7680 has two visible process ends, but its valve/instrument classification
remains unproved. Review its actual material/source evidence before correcting
the family. Retaining an unresolved exception records a reason; it does not
waive the missing engineering fact.

## 2. Review continuations

**Review source reference** shows each printed reference, source anchor and
saved decision. The curated source contains four references. Reject an
unsupported match or declare an external boundary with a specific reason and
evidence when the peer is absent or belongs to external equipment. Reopen the
decision when new evidence arrives.

For an internal match, use **Review printed XYZ** to inspect and explicitly
accept each depiction's own signed E/N/S/EL coordinate texts and tolerance.
Then use **Review continuation** to compare the full line, nominal size,
interface/topology and independent coordinates. Exact XYZ alone is insufficient
proof of connection. A discrepancy of at least 25.4 mm on any axis remains blue.
An accepted identity retains every sheet instance and retired-point alias;
source changes invalidate its proof. Never merge a flange face with a different
nearby process point just because their labels look related.

## 3. Supply dimensions, routes and stations without mixing them

**Add source dimension**, **Review printed XYZ** and the COD controls accept
explicit signed engineering evidence. Unknown axes stay null; proposed graphic
anchors never become engineering millimetres. Accept solved geometry only after
its source evidence and conflicts have been reviewed.

Use **Along-route stations** for printed along-centreline distances. The four
real support-gap proposals are unsigned until the engineer confirms their
endpoints and direction. Select the explicit source format for isometric
notations such as `2.1/8"`; it means 2 1/8 inches only under the declared
inch dot-fraction convention. Do not parse it as a decimal or infer its mapping
from nearby text.

Use **Review graph and numbering** to declare each independently inspected
point's full line, main/branch route, order and existing main-tee takeoff.
Preview the graph, then apply the exact reviewed batch. Unselected points remain
unassigned and blue. The schematic's spacing has no physical meaning.

A station chain needs its reviewed route and an explicit datum before it can be
applied. **LOCAL_ORIGIN** declares a relative station zero; it does not discover
an unknown station or establish absolute XYZ. Review conflicts, then use
**Apply station solution** only for qualified points. The six-inch flag compares
accepted, comparable along-route support stations at **152.4 mm or less**;
Euclidean XYZ separation is not that station distance.

Numbering uses the main series 10, 20, 30…; branches start at the next hundred
and additional full lines at the next thousand. A continuation keeps one number
on every sheet. The numbering map/history retains UUIDs, source instances,
stations, evidence and reasons during an unchanged numbering rerun.

## 4. Finish materials and schedules

Open **Review catalogs and schedules**. The classified source inventory has six
flange/valve rows covering **13 flanges and five valves**: two rows on sheet 1,
four on sheet 2. The separate PV classification issue is not counted as a valve.

If the reference data is not registered, upload the exact
[627-row flange workbook](../fixtures/catalogs/README.md) in **Component catalogs**.
Its four datasets are prepared for review, never automatically approved.
The workbook is a reference source: its rows are estimated and facing is
unspecified; API bore
must stay separate from pipe NPS and pipe bore. These limitations do not support
an exact match to the drawing's RTJ/type requirements. Available valve data also
does not establish the actual valve weights or lengths.

Prepare proposals, inspect source limitations and either accept a supported
unique match from an approved dataset or record **Explicit N/A** with a reason.
For the current unproved source case, all six rows retain N/A technical values.
N/A is an unresolved data disposition, not zero or engineering approval.
W_flange, W_half and W_full are alternative bare/half-bolting/full-bolting totals;
do not add the totals together or add bolting twice to an assembly weight.

Manufacturer evidence has its own decision and history. Even an approved
manufacturer-quality catalog row does not identify the component actually
supplied to this project. Obtain and review its vendor/model evidence separately.

## 5. Review the actual native PDF layout

Choose **Review native PDF layout → Generate native layout preview**. Inspect
both source sheets, zoom and pan. The displayed PDF is the server's native
annotation output, rather than an approximate overlay. Check source dimensions,
materials and NORTH, point bubbles/leaders, separate X/Y/Z and moment objects,
schedule rows/borders, blue reason warnings and the draft notice.

Record layout evidence and **Accept graphical placements** only after opening
both preview sheets. This accepts presentation positions only. Download the
native preview and annotation manifest, or generate the normal review bundle.
New source/context changes can make the graphical review stale.

The focused local 47-point case produced **285 individual additions**; this is
an observed software-test count, not a target for every project revision. Every
added object was edited and reopened through a PDF library while original raw
and decoded page streams remained byte-identical. Desktop-editor qualification
and universal compatibility with every PDF editor are not claimed.

## 6. Export review data and assess the remaining CII gate

**Export Excel (.xlsx)** and **CSV tables (.zip)** provide the same source-linked
node, element, support, component, exception, continuation, station, catalog and
native-input tables shown in Excel results. Unknown numeric cells remain blank.
Use the bundle for the annotated PDF, manifest, project snapshot, histories,
numbering map, component-review data, CSVs and readiness evidence from one
revision. An incomplete model includes a readiness report rather than a fake CII.

Use **CAESAR export settings**, element rows and **CAESAR component data** for
explicit code/origin/operating properties and component inputs. Draft records
can save missing-data evidence with null technical fields. Reviewed fields do
not waive source, geometry, topology, manufacturer or approval gates.

The current native candidate supports documented straight pipe, rigid
valve/flange records, the bounded B31J welding-tee contract and basic grounded
translational restraints. Tee factors/code-note options and each restraint's
type, target axes, stiffness, gap and friction require explicit evidence; a
rigid needs actual total weight force in N and its declared scope.

**The original native bend requirement remains unmet.** BEND output is blocked
by the unresolved CAESAR II 15.1 field-layout and COD/native-node geometry
contracts. Entering a COD, radius, note or checkbox cannot waive that block.
See [the component contract](CII_151_COMPONENT_CONTRACT.md). The actual 1010
model also retains unproved engineering data and therefore has no ready CII.

A CAESAR II application import/round trip and stress analysis have not been
performed. Native files are candidates only. Finish the outstanding source and
engineering evidence, verify the required native contract, validate the target
application and complete the applicable independent review before modelling use.

The missing original/golden generator and assets have their own regression gate.
They do not prevent this reviewed drawing workflow, and its source observations
must never be presented as the missing golden model.

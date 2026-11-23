# Reviewed continuation and bend geometry — 0.7.0

Patch 0.7.1 addresses a live-observed PDF cancellation error during sheet/view
changes. Source and preview downloads use an owned abortable same-origin
request before passing the bounded file bytes to the renderer. This requires
the complete PDF download before its first page renders. Delayed cancellation,
reopen and visible HTTP-failure behavior are exercised in the browser; provider
processing and engineering rules are unchanged.

The drawing-pack workflow and bounded DigitalOcean page jobs are unchanged.
This release adds pure engineering rules on hosting; it needs no extra paid
service, always-on worker or infrastructure.

## Continuations

Processing finds local CONT.ON/FROM/TO and MATCHLINE references. The
**Continuation sources** table retains their actual text and sheet provenance;
reciprocal references are proposals, not accepted connectivity. A printed sheet
identity is distinct from a PDF page number. Unresolved references stay visible.

In Excel results, use **Review continuation** to compare two source points on
different sheets of the same full line. Declare nominal sizes and the tolerance.
Each endpoint needs independent accepted absolute XYZ evidence. X is East, Y is
North and Z is elevation. Source text, units and fractions are retained. The
source-dimension dialog has an explicit `ISO feet/inches dot fraction` convention
for forms such as `E 146'11.5/16"`; the ordinary grammar never guesses this form.

Comparison reports all signed axis deltas. A difference of 25.4 mm or more on
any axis, inclusive, requires engineer confirmation. Smaller discrepancies and
within-tolerance differences remain review exceptions; no coordinates are
averaged. Only exact, independently proved equality can currently become a
reviewed shared physical identity. The reviewer must also confirm topology and
the physical interface; equal coordinates alone do not prove connectivity.

Acceptance retains one physical UUID and every source depiction, archives
retired identities, and rewires component ports, dimensions, elements and branch
references. It preserves an already established identity when adding a third
depiction. Conflicting stations, opposite component ends, nonzero collapsed
elements, duplicate route visits and unsupported loops are rejected atomically.
Both sheets display the same current node number. Evidence/anchor changes make
the link provisional and blue again. Withdrawal retains identity/history for
review; revalidation requires current independent direct XYZ on every depiction.

## Theoretical bend COD

The **Review bend COD** action requires a reviewed elbow association with an
explicit source convention defining COD as the theoretical straight-centreline
intersection. It uses two ordered physical XYZ points on each straight leg.
These are accepted engineering dimensions, never page coordinates or angles.

Exact rational intersection rejects parallel, skew, wrongly ordered and
insufficient legs. An unrepresentable exact decimal becomes a precision review
exception. Conflicting independently accepted COD coordinates block the
proposal. **Accept proved COD coordinates** is explicit. Its three derived
constraints retain the source inputs, association and convention fingerprint.
Changed source evidence invalidates the derivation and requires fresh review.

**Accept solved XYZ** can then populate the existing CAESAR input table. This
does not establish along-route stations, bend radius, material or operating
conditions; unknown fields remain blank. It does not enable native bend export.

## Outputs and rollback

Website and editable XLSX share **Continuations**, **Continuation sources** and
**Bend COD**, in addition to the existing Dimensions, Coordinates, Component ports
and CAESAR input tables. Known engineering values are numeric cells, with
original evidence retained separately. Native PDF objects have unique IDs,
including when a previously annotated source is uploaded again. The PDF
manifest identifies the physical UUID behind each point's leader/bubble/number.

Release security contract 3 prevents rollback to code that would ignore current
continuation identities or COD-derived evidence. Compatible code rollback and
private updater backups remain available; project edits are not reverted by a
code rollback. Golden fixtures and target-application evidence remain separate.

## Evidence and remaining acceptance

Domain, API and Chromium fixtures exercise exact/different/missing coordinates,
shared identity and source invalidation, reviewed COD acceptance, refreshed
numeric XLSX and retained unknown values. Synthetic source fixtures are labelled
as such. A real reviewed-PDF test selects, edits, saves and reopens every added
annotation type using a PDF library while checking original content streams.
This is not an Adobe/Foxit desktop round trip or CAESAR II application import.

The original legacy generator/tests, original/golden 1010 files and valve
workbook remain missing. Generic automatic point/topology/station reconstruction,
complete native component profiles, editor qualification, revision/loop rules
and the original production/security/restore gates are unfinished. The
straight-pipe CII candidate remains application-unqualified and blocks
unsupported components. See PLAN_EXECUTION.md and CII_READINESS_CHECKLIST.md.

# Physical interfaces and signed dimensional evidence

Version 0.7.0 adds reviewed continuation identities, signed cardinal source
coordinates and exact theoretical COD from independently proved engineering
legs. See [the workflow and limitations](ENGINEERING_CORE_07.md). These extend
the interface model below; they do not infer physical distances from page XY.

Version 0.6.2 adds **Detected features** in the drawing inspector and the shared
**Source features** website/Excel sheet. The bounded
`iso-weld-neck-plate-v1` recognizer compares a thin flange plate, a separate
filled pipe dot and collinear heavy linework. On the supplied 1010 PDF it finds
4 flange symbols on sheet 1 and 9 on sheet 2, with 26 distinct proposed interface
locations. It does not read a fixture-specific coordinate/count map.

Blue graphical markers are review proposals. Inspect a face or pipe dot to
prepare an editable point at that actual source location; confirm its route and
order before saving. Physical stations remain blank until independently proved.
Reopening the saved candidate selects that point rather than creating another.
The graphical feature table labels PDF X/Y as **points, graphic only**, separate
from engineering millimetres. Recognition neither associates a material row nor
merges neighbouring/shared interfaces or establishes connectivity across a gap.
Ambiguous markers and unsupported symbol conventions remain unresolved. Existing
projects need explicit source re-extraction to obtain this new evidence field.
The private DigitalOcean action is rebuilt automatically when its code changes.

Version 0.6.0 adds three shared website/Excel sheets: **Component ports**,
**Dimensions** and **Coordinates**. The existing drawing-pack workspace and
DigitalOcean page processing remain the same.

The materials inventory automatically prepares bounded component occurrences:
two physical ends for a flange (face and opposite pipe black dot), two process
ends for a valve or inline instrument, one for a single-ended PIT, one main-run
tee intersection, one theoretical elbow COD and one per support station.
Ambiguous instruments require classification; unknown counts and occurrences
over the explicit cap remain exceptions. Preparing requirements never fabricates
physical points, stations or source anchors.

Open **Component connections** in Excel results, or select a Component ports
row. Associate each required interface with an existing physical point on the
correct full line, inspect the source feature and record evidence. A flange and
adjacent valve reuse their shared point UUID. Opposite ends cannot share a point
or an equal station on the same route. Multiple genuinely coincident supports
can associate with one physical node; mere proximity never merges them.

The association captures a source-page box around the point's unrotated anchor,
page content hash, original PDF hash and human evidence. Moving its bubble does
not change physical evidence. Moving its anchor outside the inspected feature,
changing source content or changing classification requires fresh association
review. An elbow needs the dimension convention proving theoretical COD; a
diagram bend or drawing-pixel angle does not prove COD.

Use **Add source dimension** for an explicit signed X/East, Y/North or
Z/elevation coordinate or difference. Preserve source units/fractions and state
the tolerance and source evidence. The Decimal solver evaluates each axis
independently, retains its constraint/evidence groups and rejects contradictory
chains/anchors. Unknown absolute origins remain blank; a relative solution
shows its own basis and is not presented as a surveyed coordinate. Unknown
axes are never filled with zero. No PDF scale, page XY or bubble position is used.

Complete solved element XYZ vectors can be explicitly accepted into the existing
CAESAR input sheet. Pipe properties and accepted route stations are retained.
Existing manual vector inputs are retained as source constraints. Later source
changes make accepted solutions stale; conflicting/stale geometry blocks native
export. Component auxiliaries are not emitted by the first straight-pipe-only
CII profile. Workbook/CSV tables remain useful review handoffs with numeric cells
and blank unknown values. The review ZIP also includes `physical-model.json` and
`dimensional-solution.json` for traceability.

Review scopes bind physical connections, association checks, source dimensions
and element properties. The inclusive 152.4 mm support rule applies to physical
support associations, including a support sharing a node with another feature.
It uses accepted along-route stations, not page distance. A signed XYZ chain
does not automatically prove a curved along-centreline station or an elbow.

Current bounds are 1,000 component occurrences, 2,000 solver points and 6,000
source/element-axis constraints. Exceeding a bound reports an incomplete model;
it does not silently discard requirements or call an export verified. The pure
rules/solver run cheaply on hosting; heavy document extraction/OCR uses the
bounded DigitalOcean worker.

Original remaining gates include general arbitrary-PDF symbol/graph recognition,
automatic intersheet continuation proof, complete station/COD inference,
manufacturer/valve source data, original 48/49 fixtures and actual supported
CAESAR/PDF-editor round trips. This release does not turn an unreviewed drawing
into verified stress input. See `PLAN_EXECUTION.md`.

## Clean workspace after tests

The hosting administrator can preview **Start a clean test workspace** in Admin
connections. Clearing requires an exact current preview and typed confirmation;
an enabled authenticator also requires recent factor assurance. Active jobs or
cloud transfers prevent reset. It archives the current database and project
files privately, then removes active projects, drawings, exports, review issues
and clearly labelled temporary software-test accounts. Ordinary failures roll
back SQL and restore earlier file moves.

Genuine logins, the flange reference library, provider/updater settings,
diagnostics and paid-use counters remain. Private reset backups are outside the
web/code directory in `reset-backups/<backup-id>/`: owner-only database/manifest
and archived files. These backups are permission-protected, not encryption at
rest or off-site disaster recovery. A process kill or machine failure during
reset needs operator-assisted recovery using that manifest/database/files; no
automatic wholesale restore over later genuine work is performed.

Downgrades that would ignore active physical-model safeguards are refused.
Compatible code rollback still preserves current project data. Failed packages
and manually reverted releases are held from automatic reinstall; a new release
remains eligible, and an explicit Install update can retry the selected package.
The automatic-update preference stays enabled. Original
production storage, malware scanning, licensing and disaster-restore gates
remain visible in the execution ledger.

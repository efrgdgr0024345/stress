# Architecture and contracts

## Layout

```
apps/web/src/             React interface, PDF.js viewer and SVG editing
services/api/            FastAPI, SQLite persistence, bounded parser worker
packages/engineering/   Exact units, numbering, reasons, route topology, validation
packages/pdf/           Native PDF export and synthetic fixture adapter
tests/unit/             Pure engineering regression checks
tests/integration/      Authentication, upload, revisions, native PDF tests
tests/e2e/              Built-site Chromium workflow
```

The source planning PDF is recorded as `CODEX_MASTER_PLAN.txt` (text extracted with `pdftotext -layout`). It is a requirements source, not evidence that its referenced files or acceptance results exist in this repository.

## Coordinates and identities

Physical stations are nullable decimal millimetre strings parsed from explicit units. Raw input precision is preserved by Decimal arithmetic; the original text/evidence is retained in immutable command revisions/audit context where present. No display coordinate participates in a station calculation. Local coordinates in source PDF points are relative to the unrotated CropBox top-left. The browser converts through the actual PDF.js page view and viewport rotation; inverse conversion is used for pointer events. Export uses PyMuPDF's corresponding unrotated page coordinates.

Each physical point has one UUID and one integer number, and one or more sheet instances. Each instance has independent anchor and bubble coordinates. The source revision, engineering evidence, physical point identity and stable native object names are included in each export bundle. A branch's takeoff references the already existing main-run tee UUID, never a second tee.

Route order is explicit engineering input, independent of sheet order. Number complete main runs first, branches sorted by main-run takeoff order, reserve the next hundred boundary after the last allocated branch value, and allocate later lines at the next thousand boundary after the previous line's maximum. Duplicate route order is an exception, not silently accepted as a verified physical sequence.

## Mutations and persistence

Each mutation supplies the current project `version`. A SQLite `BEGIN IMMEDIATE` transaction checks tenant ownership and the optimistic token, writes the complete updated model, inserts an immutable revision snapshot, and records an audit event. Stale writes return 409. Original source file bytes are never overwritten. Every export is an immutable artifact keyed by project/revision; repeat requests return the existing artifact. Sessions are stored by SHA-256 of opaque random cookies.

SQLite schema initialization is idempotent and marked `user_version=1`. A production migration adapter and external database are pending. The JSON aggregate favors a reviewable local MVP over premature relational migrations for absent legacy data. It is not an implementation of PostgreSQL row-level security.

## Native PDF export

Source pages are copied with existing annotations retained. Added Circle, FreeText, Line and Square annotations get stable `/NM` identifiers scoped to project/sheet/physical group/role. Draft notices, separate triad text/lines, schedule rows and borders are native objects. No added annotation is painted into source page content. The output is reopened and original stream hashes and every new annotation identity are checked before creating the ZIP. A failure aborts artifact creation.

Unknown engineering properties are never initialized to zero. Current schedules state N/A and missing catalog status; legacy example weights are not used. All output is a review draft. `qa.json` explicitly distinguishes automated structural checks from the unperformed designated-editor test.

## APIs

`/openapi.json` is generated from typed Pydantic request contracts. Principal endpoints are under `/api/v1`:

- `auth/me`, `auth/local`, `auth/login`, `auth/logout`
- `projects`, `projects/{id}`
- `projects/{id}/sources`, `sources/{source_id}`
- `projects/{id}/sheets/{sheet_id}`
- `projects/{id}/nodes`, `nodes/{point_id}`, `nodes/renumber`
- `projects/{id}/graph`, `validation`
- `projects/{id}/materials`, `materials/{item_id}`
- `projects/{id}/review`, `audit`, `exports`, `artifacts/{id}/download`
- `catalogs`, `catalogs/import`

No endpoint grants verified-for-modelling approval. Workbook intake is admin-only and returns `PENDING_SCHEMA_REVIEW`. Every project/file/artifact operation checks its tenant-scoped project first. Missing cross-tenant objects return 404. Viewer-role writes return 403. The local account is a development convenience, not an authentication strategy for public hosting.

## Version 0.2 additions (superseding the initial MVP restrictions above)

`packages/catalogs` now handles explicit source mappings, normalized values, exact matching and source-derived schedules. SQLite schema version 2 adds `catalog_versions` without replacing prior data. Catalog registration remains immutable intake; each mapped range creates a version that is separately inspected and approved. Approved records are never remapped in place. Match snapshots retain the source/workbook hashes, normalized-record hash, approval, specification constraints, record and reason in the project revision. Reference quality cannot become project manufacturer confirmation unless both vendor and model are constrained by drawing evidence.

`services/api/workflows.py` registers catalog previews/versions/approvals, matching/clearing, schedule preview, revision comparison/download/recovery, native drawing annotations, authenticated artifact PDF preview and public lessons documentation before the static website mount. All engineering mutations use the existing project version transaction. Restoring a revision copies its model into a new draft; it never overwrites prior snapshots or approves restored evidence.

The root `loader.php` is a portable HTML/PHP view with safe DOM text rendering. Its same-origin project API remains authenticated. Its lessons register contains public project documentation and is exposed independently of private drawings. A PHP interpreter is not needed when the view is served by FastAPI. The browser loader's project link is read by the React application to open the chosen drawing workspace directly.

Generic graphic notes are stored by stable ID, sheet, native annotation kind, unrotated PDF rectangle/endpoints, colour and text. Their native counterparts use stable annotation names in export. They do not participate in station/length calculations. The generated PDF preview reads the actual artifact, not a reconstruction of the source overlay.

The existing export/approval limitation remains: outputs are review drafts and do not assert final engineering verification. Browser and structural PDF checks do not guarantee every third-party editor's behavior. Production database/object-storage/queue and identity adapters are still pending.

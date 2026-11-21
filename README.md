# CAESAR ISO — Engineering review workspace

A working browser-based piping-isometric review system built from the attached engineering plan. The website displays the original drawings and lets an engineer edit physical points, bubbles, leaders, drawing notes and shapes, reconcile materials, match approved catalog records, recover earlier revisions, and preview or download native annotated PDFs.

The interface uses a consistent macOS-inspired appearance. The root [loader.php](loader.php) opens projects directly in the drawing workspace and displays every entry in [LESSONS_LEARNED.md](LESSONS_LEARNED.md) immediately beneath its **Load project** section. Both files are maintained in GitHub. Editing the Markdown register updates the displayed lessons without rebuilding the frontend.

Screenshots from the synthetic test project: [macOS-style loader and lessons](docs/screenshots/loader.png) · [in-site generated PDF preview](docs/screenshots/export-preview.png).

## Start the website

Requires Node.js 24 and Python 3.12. Run these commands from the repository:

```bash
./scripts/setup.sh
./scripts/start.sh
```

Setup creates an isolated `.venv`, installs pinned Python requirements and the npm lockfile, builds the site, and runs the API/domain tests. Start serves the API, the built website and `/loader.php` on **port 3000**. Open the environment's browser/preview at that port. Choose **Enter local workspace** to use the local demonstration account. `PORT` and `BIND_HOST` override startup binding.

The loader is a portable HTML/PHP view: it can be served by this application without a PHP interpreter, or by a PHP-capable host that routes `/api/v1` to the running CAESAR API. GitHub stores source files; it does not execute the application. A standalone copy can display the adjacent Markdown lessons file, but needs the API to load private project drawings.

The loader now includes **Download cPanel ZIP** and **Install on cPanel** controls.
The [downloadable package](downloads/caesar-cpanel.zip) includes the built website
and a Passenger WSGI entry point. Follow the [cPanel installation guide](docs/CPANEL.md).
It requires Python 3.12 hosting, HTTPS and a private data directory; PHP-only
hosting is insufficient. Keep the deployment restricted to a private pilot
while the documented production security work remains. Rebuild the ZIP after
source changes with `npm run build && python scripts/package_cpanel.py`.

Both a domain root and a subdirectory such as `https://easyai.com.au/stress/`
are supported. Assets, navigation, API calls, PDF URLs and session cookies stay
inside the application mount. Passenger's public URL mapping points to private
application code outside `public_html`; drawings and credentials also stay
outside the public directory. The CLI configuration helper prompts for
credentials and saves an account-private file with mode 600.

For frontend development, run `npm run api` (port 8010) and `npm run dev` (Vite on port 5173) in separate terminals. Vite proxies authenticated API requests. Workspace dates use Australia/Perth; override `VITE_WORKSPACE_TIMEZONE` at build time for another workspace timezone.

Alternatively, `docker compose up --build` starts the application on **127.0.0.1:3000** with retained private data in a named volume. The Linux Compose configuration supplies the host CA bundle as a temporary build secret; set `CAESAR_CA_BUNDLE` if its location differs. TLS verification remains enabled and the bundle is not copied into image layers.

## Daily engineering workflow

1. Create a project with its full line ID. Upload PDFs (30 MB / 100 pages per source, 200 pages per project). Confirm printed sheet identities in Drawing register. The original source bytes and SHA-256 are preserved.
2. Open Drawing workspace. Every page is rendered inside the website with zoom, pan, page switching and an editable overlay. **Add point** places a provisional marker; assign main/branch order and component type explicitly. Branches reference an existing main-run tee.
3. Enter engineering stations with explicit units, for example `1200 mm`, `2 1/8 in` or `3' 2"`, and source evidence. Unknown stations stay null and blue. Drag graphic bubbles/anchors separately: paper coordinates never establish a physical dimension.
4. Use **Drawing annotations** for editable text, rectangles, circles and lines. Click an object on the drawing to edit its text, colour or position. These graphic notes do not change physical stations.
5. Reconcile materials with the original drawing. Add, correct or remove inventory rows. Match flange/valve specifications against an approved catalog dataset; see the controlled catalog workflow below.
6. Place axes and schedules in clear areas, inspect all sheets, and review exceptions. The website shows source-derived numbers and quality labels; unsupported values remain N/A.
7. Generate a review bundle and use **Preview generated PDF** to inspect the actual native PDF inside the website. Download the ZIP when ready.
8. Inspect history, compare revisions, download a model snapshot, or restore an earlier revision as a new draft. Existing snapshots and earlier exports are retained.

The synthetic two-sheet training project is clearly labelled and is not the missing legacy 1010 drawing. Its sample stations are not real engineering evidence. The system does not infer physical lengths from NOT-TO-SCALE graphics.

## Controlled catalog workflow

1. An administrator registers a non-macro XLSX workbook. The original is privately retained with a source hash and sheet inventory.
2. Map source columns or explicit constants, choose the worksheet/header/data range and select source weight/length units. Inspect the normalized records and any errors. Missing numeric fields remain null.
3. Approve an error-free dataset with a review reason. Approval freezes that version; remapping creates a new version.
4. In Materials, choose **Match catalog** and enter full specification keys. API 6A requires a true API bore separate from pipe NPS. Zero matches and multiple exact candidates are rejected; no nearest-value substitution occurs.
5. Save a unique match with evidence. A complete source row, original workbook hash, normalized-record hash, dataset approval and match reason are copied into the project revision. Updating a catalog never replaces historical project values.

The canonical target fields are described by `/api/v1/catalog-schema`. Required fields include `family`, `standard`, `rating`, `nps`, `component_type`, `source`, and `quality`; flanges also need facing, valves need end connection, and API 6A needs API bore. Numeric weights are in N and lengths in mm. Explicit kg/lbf or inch source mappings record the conversion. For `BARE_FLANGE` scope only, supplied studs/nuts/count can derive half and full bolting allowances; assembly-included weights are never bolted twice.

Catalog source quality and actual manufacturer confirmation are separate. Even a manufacturer-confirmed reference row stays **REFERENCE_ONLY** for the project until the drawing/vendor evidence explicitly identifies the matching manufacturer and model. Unknown actuator scope and missing properties remain visible exceptions.

## Exports and compatibility

ZIP bundles contain the annotated PDF, node CSV, complete project JSON, material schedule, catalog provenance snapshots, exception report, numbering map, native annotation manifest and structural QA report. Each added label, circle, leader, text note, shape, axis primitive, schedule row and border is a native PDF annotation. Original page content streams are compared after serialization. Text and tables that do not fit their boxes fail export rather than disappearing silently.

The website is the primary drawing editor. Exports use standard annotation types for broad PDF-editor compatibility. Reader/editor capabilities vary; universal editing support across every PDF application cannot be guaranteed. Automated checks exercise native object editing/reopening and actual generated-PDF rendering in the browser. No Adobe-only dependency is imposed.

Exports are **engineering review drafts**, not verified-for-modelling approvals. Materials/stations still need professional engineering review; entering evidence does not automatically certify its correctness.

## Validation

```bash
npm run build
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/e2e/smoke.py
```

The browser test requires Chromium at `/usr/bin/chromium` (or set `CHROMIUM_PATH`). It starts a disposable server and private temporary storage, then exercises the actual built site, loader and all lessons, annotation editing, workbook mapping/approval/matching, PDF preview/download, rotated CropBox handling, reload persistence and mobile layout. It does not modify normal project data. See [validation evidence](docs/VALIDATION.md).

## Data, security and production boundaries

Private data lives in ignored `.local/` by default; `CAESAR_DATA_DIR` changes the location. SQLite migrations are additive and retain prior projects. Stop the application before backing up this directory, including original sources, workbooks, SQLite and outputs. Do not commit runtime data or serve the repository root as an unrestricted public web directory.

Local mode (`CAESAR_LOCAL_DEMO=1`, default) supplies a local administrator account without a password. Keep it private. For authenticated mode use `CAESAR_LOCAL_DEMO=0`, `CAESAR_ADMIN_EMAIL`, and a secure `CAESAR_ADMIN_PASSWORD` of at least 12 characters; `CAESAR_SECURE_COOKIE=1` requires HTTPS for cookies. Sessions are opaque, HttpOnly, SameSite=Strict and expire after 12 hours. Every project/artifact/catalog operation checks server-side permissions and tenant scope. The lessons register is deliberately public documentation.

This is a local/manual engineering-review system, not a full stress solver or a completed enterprise SaaS. Remaining production work includes OIDC/MFA and team administration, independent approvals, isolated no-network parser workers, malware scanning, durable jobs, production database/object storage, managed backups, monitoring and external-editor qualification. PDF parsing has resource limits and active-content rejection, which are not a malware sandbox.

Only the planning PDF was supplied. The v1.2 generator, original 1010 source/review fixtures, 13 legacy tests and canonical flange/valve workbooks remain absent. Their numerical and 48/49-node regression gates are unrun. See [implementation status](docs/IMPLEMENTATION_STATUS.md) and [architecture](docs/ARCHITECTURE.md).

Resolve PyMuPDF's AGPL/commercial licensing before a proprietary hosted release. The PDF adapter remains isolated for replacement. No production deployment or environment publication is performed by the setup scripts.

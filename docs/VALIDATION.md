# Validation evidence — 0.4.0

The application has a repeatable validation path rather than relying on an already-running demo process:

```bash
./scripts/setup.sh
.venv/bin/python tests/e2e/smoke.py
```

Setup performs a clean virtual-environment dependency install, locked npm installation, TypeScript/production build and API/domain tests. Browser tests run against the built site and temporary private storage, leaving user projects intact.

## Automated coverage

The API/domain/hosting suite passed **114 tests** locally with no skips and retains the original unit, upload, authorization, revision, numbering, native-PDF and coordinate regressions, plus catalog mapping, controlled approvals, units, unknown values, bolting scopes, ambiguity rejection, source integrity, independent project manufacturer confirmation, immutable source snapshots, free annotations and revision recovery. Version 0.4.0 adds pipeline, workbook, native-format and worker-isolation regressions described below.

The cPanel package test extracts the actual downloadable ZIP, verifies its file
hashes and absence of private/runtime directories, and uses its Passenger WSGI
entry point over simulated HTTPS to sign in, upload a synthetic PDF and export
a native review bundle. It verifies refusal of unsafe hosted configuration and
checks private paths. A separate regression rejects existing demo sessions
after demo mode is disabled. Chromium also opens/closes the cPanel guide and
downloads and inspects the ZIP using the visible loader button.

These checks passed locally with the PyMuPDF 1.26.7 update. They do not verify a
particular cPanel account, its Apache document roots, quotas or provider support;
those still require the installation checks in `docs/CPANEL.md`.

The Passenger package regression exercises both a domain root and `/stress/`
using WSGI `SCRIPT_NAME`, including mount-scoped login/logout cookies. It also
tests private CLI configuration, file mode 600, refusal of readable credentials,
refusal to overwrite an existing configuration and no password in command
output. Browser tests can run the complete workflow under the same prefix:

```bash
CAESAR_TEST_MOUNT=/stress .venv/bin/python tests/e2e/smoke.py
```

Browser coverage includes loader navigation, every lesson card/icon, direct project-to-canvas loading, original PDF rendering, native drawing-note creation/editing, graphic-only node edits, exact stations/support reasons, provisional points, route overlay, page/zoom controls, material review, workbook upload and source mapping, normalized record inspection, approval, exact match saving, exceptions, native bundle download, generated-PDF preview, rotated/nonzero-CropBox input, saved project reload and mobile navigation/layout.

The native PDF checks enumerate stable object names, edit/save/reopen representative types, retain original content streams, and inspect actual source-derived schedule text and provenance. The generated PDF is also opened by the browser's independent PDF renderer. No test result is a claim of universal editing support in every external PDF application.

## Command-line installer

Six additional tests cover the account-level installer using a simulated
CloudLinux Selector and a real local HTTP server: first installation, repeat
runs, backups, preserved credentials/data, provider startup templates,
dependency failure and resume, application conflicts, checksum/path rejection,
private diagnostic logs and public-folder URL verification. Existing tests
continue exercising the real Passenger adapter and PDF workflow. See
[command-line setup](CPANEL_COMMAND_LINE.md). The tests do not constitute an
installation on the user's hosting account.

Three further checks distinguish a web-server HTML 404 from application startup
failure without blind retries, and verify that diagnostic output redacts known
secrets and omits environment/rewrite values. The hosting diagnostic uses the
installed Python environment with a temporary private database; it does not
change real project data or web-server routing.

Six routing-repair tests simulate web-server responses and check exact backups,
scoped rewrite matching, preserved PHP/source data, code-directory permissions,
explicit WSGI fallback, reruns and rollback. These are filesystem/control-flow
checks, not an emulation of Apache/LiteSpeed. See
[routing repair](CPANEL_ROUTING_REPAIR.md). Actual-host health/frontend checks
remain necessary.

A real fork regression checks cold and warmed WSGI parent processes: forked
workers must complete an authenticated health request before an alarm expires.
The old import-time adapter hung in the reproduction; lazy per-process adapter
initialization passes. Four installer checks exercise automatic routing recovery
for unavailable hosting, refusal to recover routing for login/access failures,
and refusal to execute a recovery script with an unexpected checksum.
See [worker startup fix](CPANEL_WORKER_FIX.md). The real provider's startup
error remains necessary if the corrected app still fails there.

Six administrator-recovery tests exercise the real API password/session
implementation with disposable data: updated login, session revocation,
unchanged projects, configuration synchronization and private backups,
duplicate-email rejection, readable-config/short-password refusal, rollback
on file-write failure and no password in prompt output. See
[administrator recovery](ADMIN_RECOVERY.md).

## Container trust and execution

The Dockerfile supports an optional `proxy_ca` BuildKit secret at dependency-install steps. It adds trust for the managed session proxy while retaining certificate verification. The secret bundle is not committed or copied into image layers. Compose supplies the Linux host bundle from `/etc/ssl/certs/ca-certificates.crt`, configurable with `CAESAR_CA_BUNDLE`.

The container runs as a non-root user. CI and documented commands validate builds, API/domain behavior, real Chromium behavior and Compose syntax. Run container checks with dropped capabilities, no-new-privileges and a read-only test mount to verify the deployed dependency set. Private runtime data is never committed.

## Unrun external gates

The original 13 legacy tests, original 1010 48/49-node fixture, authoritative workbook numeric regressions, universal third-party editor coverage, actual engineer/lead sign-off, production OIDC/MFA and queue/storage/DB infrastructure and disaster-restoration drills have not been established. Their required assets, credentials or operational decisions were not supplied. The existing hosting pilot has been installed, but each new release still requires actual-host verification by its operator.

Publication and deployment are distinct from a source commit or a local test. No public deployment or environment publication is performed automatically.

## Automatic pipeline and spreadsheet outputs

The unattended synthetic two-page profile runs intake through registration,
evidence, source-derived point/material proposals, native PDF and editable XLSX.
Integration checks cover duplicate/quarantine cleanup, expired leases and
fences, cancellation during publication, project serialization, source revision
replacement, unchanged-page reorder, correction outbox/deletion retention and
authorization before multipart body reception. Unknown/inconsistent dimensions
remain unaccepted. Route tests reject loops/disconnections and distinguish
crossings from proved junctions.

Workbook checks reopen editable files, inspect numeric/unknown/exact cells and
Excel tables, preserve literal formula-like text, reject external links/macros,
keep element geometry separate from station proposals, require all active edges,
preserve length units separately from component counts and protect immutable
artifact/tenant access. Native CII tests independently parse fixed-width version,
counts, geometry, material IDs, allowables, units and coordinates, and reject
missing/conflicting properties or unsupported components. They do not execute
CAESAR II; application import qualification remains open.

The real Docker supervisor is tested for absence of host private files, inherited
website credentials, external networking and root-filesystem writes. A separate
test rejects an active JavaScript PDF within that worker. These tests require
`caesar-worker:local` and are explicitly skipped if it is absent; CI builds it
before testing. Landlock support must be qualified on each hosting kernel.

Chromium exercises the Project flow timeline, unaccepted station proposals,
website spreadsheet tabs, evidence-backed element edits, actual XLSX/CSV
downloads, gated CII settings and mobile table overflow. The real reviewed 1010
PDF also completes OCR and review export without fabricated engineering nodes.
An opt-in `CAESAR_TEST_ARTIFACTS_DIR` retains its generated workbook/CSV/report.

Updater tests cover admin access, queued command serialization, archive/hash rejection, failed-health restoration, interrupted-swap recovery and data-preserving manual rollback. Browser coverage opens the System updates panel and checks disabled installation before runner setup. These use simulated deployment health; actual cPanel cron/restart/update still requires operator verification.

Ten diagnostic regressions check request/actor/phase correlation, safe stack frames, privacy of bodies/query/header/filename values, operator-only access, bounded/rate-limited browser intake, logging-failure isolation, row retention and updater event sanitization. Browser coverage exercises the Logs sidebar, filtering/details, actual structured console capture, JSON download/privacy and mobile layout. See [logging scope and limits](LOGGING.md).

Three real-file regressions pin the user-provided reviewed 1010 PDF, classify its
outlined vector pages, preserve original source bytes/content streams and test
provisional nodes, native note export and correlated diagnostics. The Chromium
workflow also uploads this actual file, renders both sheets, edits/reloads a
note, downloads the review bundle and previews its two-page PDF inside the site.
See [real drawing results and engineering limits](REAL_DRAWING_VALIDATION.md).

Release 0.4.0 checks passed on 22 November 2026: production frontend build,
114 automated tests (including the real container boundary), complete Chromium
workflows at `/` and `/stress/`, worker image build and Compose configuration.
The reviewed 1010 workflow produced two OCR pages and 32 unverified material
proposals, with no invented physical points. Actual workbook/CSV outputs are
retained under `examples/1010-review/`.

## Release 0.4.4: Functions demo and extraction recovery

130 automated tests passed locally. The exact private Functions demo ZIP also
passed the included real PDF under a 1 GiB/no-swap, one-CPU, no-network Docker
profile: 13 and 19 unreviewed material proposals, with preserved word confidence
and source identity. Package size is below the conservative 48 MB limit.
`serverless/digitalocean/evidence/local-qualification.json` records the measured
size, hashes, elapsed times and parser peak RSS. It explicitly does not claim a
live DigitalOcean test. The deployment workflow requires a secure token and
performs its own provider smoke test before publishing a live result report.
The re-extraction regression now requires completion, catching the missing
publication checkpoint exposed by the real cPanel run.

# Validation evidence — 0.2

The application has a repeatable validation path rather than relying on an already-running demo process:

```bash
./scripts/setup.sh
.venv/bin/python tests/e2e/smoke.py
```

Setup performs a clean virtual-environment dependency install, locked npm installation, TypeScript/production build and API/domain tests. Browser tests run against the built site and temporary private storage, leaving user projects intact.

## Automated coverage

The API/domain/hosting suite contains **51 tests** covering the original unit, upload, authorization, revision, numbering, native-PDF and coordinate regressions, plus catalog mapping, controlled approvals, units, unknown values, bolting scopes, ambiguity rejection, source integrity, independent project manufacturer confirmation, immutable source snapshots, free annotations and revision recovery.

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

## Container trust and execution

The Dockerfile supports an optional `proxy_ca` BuildKit secret at dependency-install steps. It adds trust for the managed session proxy while retaining certificate verification. The secret bundle is not committed or copied into image layers. Compose supplies the Linux host bundle from `/etc/ssl/certs/ca-certificates.crt`, configurable with `CAESAR_CA_BUNDLE`.

The container runs as a non-root user. CI and documented commands validate builds, API/domain behavior, real Chromium behavior and Compose syntax. Run container checks with dropped capabilities, no-new-privileges and a read-only test mount to verify the deployed dependency set. Private runtime data is never committed.

## Unrun external gates

The original 13 legacy tests, original 1010 48/49-node fixture, authoritative workbook numeric regressions, universal third-party editor coverage, actual engineer/lead sign-off, production OIDC/MFA and queue/storage/DB infrastructure, disaster-restoration drills and hosted deployment have not been established. Their required assets, credentials or operational decisions were not supplied.

Publication and deployment are distinct from a source commit or a local test. No public deployment or environment publication is performed automatically.

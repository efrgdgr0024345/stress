# Validation evidence — 0.2

The application has a repeatable validation path rather than relying on an already-running demo process:

```bash
./scripts/setup.sh
.venv/bin/python tests/e2e/smoke.py
```

Setup performs a clean virtual-environment dependency install, locked npm installation, TypeScript/production build and API/domain tests. Browser tests run against the built site and temporary private storage, leaving user projects intact.

## Automated coverage

The API/domain suite contains **34 tests** covering the original unit, upload, authorization, revision, numbering, native-PDF and coordinate regressions, plus catalog mapping, controlled approvals, units, unknown values, bolting scopes, ambiguity rejection, source integrity, independent project manufacturer confirmation, immutable source snapshots, free annotations and revision recovery.

Browser coverage includes loader navigation, every lesson card/icon, direct project-to-canvas loading, original PDF rendering, native drawing-note creation/editing, graphic-only node edits, exact stations/support reasons, provisional points, route overlay, page/zoom controls, material review, workbook upload and source mapping, normalized record inspection, approval, exact match saving, exceptions, native bundle download, generated-PDF preview, rotated/nonzero-CropBox input, saved project reload and mobile navigation/layout.

The native PDF checks enumerate stable object names, edit/save/reopen representative types, retain original content streams, and inspect actual source-derived schedule text and provenance. The generated PDF is also opened by the browser's independent PDF renderer. No test result is a claim of universal editing support in every external PDF application.

## Container trust and execution

The Dockerfile supports an optional `proxy_ca` BuildKit secret at dependency-install steps. It adds trust for the managed session proxy while retaining certificate verification. The secret bundle is not committed or copied into image layers. Compose supplies the Linux host bundle from `/etc/ssl/certs/ca-certificates.crt`, configurable with `CAESAR_CA_BUNDLE`.

The container runs as a non-root user. CI and documented commands validate builds, API/domain behavior, real Chromium behavior and Compose syntax. Run container checks with dropped capabilities, no-new-privileges and a read-only test mount to verify the deployed dependency set. Private runtime data is never committed.

## Unrun external gates

The original 13 legacy tests, original 1010 48/49-node fixture, authoritative workbook numeric regressions, universal third-party editor coverage, actual engineer/lead sign-off, production OIDC/MFA and queue/storage/DB infrastructure, disaster-restoration drills and hosted deployment have not been established. Their required assets, credentials or operational decisions were not supplied.

Publication and deployment are distinct from a source commit or a local test. No public deployment or environment publication is performed automatically.

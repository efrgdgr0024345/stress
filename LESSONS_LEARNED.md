# Lessons learned

This is the shared lessons-learned register for the CAESAR ISO workspace. The website reads this file to display lessons in the project loader. Update this file through a reviewed GitHub change when a new lesson is established.

Use the existing entry format: a unique `LESSON-###` heading, category, status, lesson, action, and evidence. Record observed outcomes; keep credentials, client drawings and confidential engineering data out of this register.

## LESSON-001 — Drawing position is not a physical dimension

- Category: Engineering integrity
- Status: Adopted
- Lesson: A point's PDF coordinates describe its graphic placement. They do not establish a physical station, especially on a NOT-TO-SCALE drawing.
- Action: Store engineering stations separately, require explicit units and source evidence, and preserve unknown stations as null.
- Evidence: `packages/engineering/__init__.py`; exact-unit and graphic-only edit tests.

## LESSON-002 — Unknown catalog data must remain unknown

- Category: Catalog quality
- Status: Adopted
- Lesson: A nearby valve or flange record is not an exact manufacturer or specification match. Missing weights and lengths must not become zero or borrowed values.
- Action: Use reviewed, versioned workbook mappings and explicit matching keys. Retain source hashes, row provenance and data-quality labels in the project snapshot.
- Evidence: The implementation plan's API 6A bore, DBB valve and manufacturer-confirmation requirements.

## LESSON-003 — Editable PDFs require native annotation objects

- Category: PDF compatibility
- Status: Adopted
- Lesson: A rendered label or screenshot can look correct while being impossible to select and edit as an independent PDF annotation.
- Action: Export standard native text, circle, line and rectangle annotations; enumerate and reopen them, and compare original source content streams. Keep the drawing editor available inside the website.
- Evidence: `packages/pdf/__init__.py`; native annotation and source-integrity integration tests. Compatibility with an individual editor requires testing that editor.

## LESSON-004 — Engineering flags follow physical identity

- Category: Node rules
- Status: Adopted
- Lesson: Renumbering a point must not change its physical station, evidence, support flag or shared continuation identity.
- Action: Use stable physical-point IDs with separate sheet representations. Apply the six-inch support rule to the downstream support at separations of 152.4 mm or less, using engineering evidence only.
- Evidence: Deterministic numbering, continuation identity and inclusive support-threshold tests.

## LESSON-005 — Test the complete browser transition

- Category: Software reliability
- Status: Adopted
- Lesson: Passing API tests did not catch a missing project-response field or a selection-state reset during point creation. Both failures interrupted the browser workflow.
- Action: Exercise project creation, upload, selection changes, editing, reload and download in a real browser with disposable data.
- Evidence: `tests/e2e/smoke.py`; the first implementation's upload and point-selection corrections.

## LESSON-006 — Container trust differs from host trust

- Category: Development environment
- Status: Adopted
- Lesson: Package downloads that succeed on the host can fail inside a container because the managed HTTPS proxy's CA is absent from the inner trust store.
- Action: Supply the session CA through a temporary BuildKit secret or a supported trust setting. Keep TLS verification enabled and keep session trust material out of repository files and image layers.
- Evidence: `docs/VALIDATION.md`; verified container build using a temporary CA mount.

## LESSON-007 — A saved filesystem does not keep services alive

- Category: Operations
- Status: Adopted
- Lesson: Environment restoration retained the application files and SQLite project data, but the web process needed to be started again.
- Action: Maintain repeatable startup instructions, check API and page readiness, and preserve existing project data during restarts.
- Evidence: Environment-resume inspection and local application startup checks.

## LESSON-008 — Sample fixtures do not validate real project data

- Category: Validation
- Status: Adopted
- Lesson: Synthetic PDFs are useful for testing software behavior but cannot prove the missing legacy 1010 counts, canonical workbook values or engineering correctness.
- Action: Label training data clearly. Keep missing source assets and unrun acceptance gates explicit, and add source-hash-pinned regressions when the real files are supplied.
- Evidence: `docs/IMPLEMENTATION_STATUS.md`; synthetic fixtures are separate from the unavailable 1010 source package.

## LESSON-009 — A catalog manufacturer is not the project manufacturer

- Category: Engineering integrity
- Status: Adopted
- Lesson: A catalog row can document a manufacturer's verified values without proving that the actual drawing uses that manufacturer or model.
- Action: Keep catalog source quality separate from project match status. Require explicit manufacturer and model constraints plus drawing/vendor evidence before marking the project match manufacturer-confirmed.
- Evidence: `test_catalog_manufacturer_does_not_confirm_the_drawing_manufacturer` verifies that an approved manufacturer row stays reference-only until the project identity is explicitly confirmed.

## LESSON-010 — A PHP loader does not install a Python application

- Category: Hosting
- Status: Adopted
- Lesson: Opening loader.php on shared hosting displays a page, but the drawing workspace also requires a running Python API, built frontend, private storage and supported hosting configuration.
- Action: Provide a complete allowlisted hosting ZIP and visible installation steps. Check Python/Passenger support, keep data outside the public directory, disable demo access and verify the deployed service before using real drawings.
- Evidence: `docs/CPANEL.md`; `passenger_wsgi.py`; `scripts/package_cpanel.py`; loader download and cPanel installation controls.

## LESSON-011 — A public URL is different from a private application directory

- Category: Hosting
- Status: Adopted
- Lesson: A working PHP loader at /stress/ does not make a root-only Python application work at that URL, and extracting the complete source into public_html would expose unnecessary private files.
- Action: Keep browser links, API requests, PDF URLs and cookies within the selected application path. Let Passenger map /stress/ to an application outside public_html, with private credentials and drawing storage. Test both root and subdirectory deployments.
- Evidence: Subdirectory browser workflow; Passenger SCRIPT_NAME package tests; docs/CPANEL.md.

## LESSON-012 — WSGI adapters must start their threads in the serving worker

- Category: Hosting
- Status: Adopted
- Lesson: An ASGI-to-WSGI adapter created during module import starts a background event loop. After a web server forks workers, that inherited loop can have no running thread, so HTTP requests hang despite a successful standalone startup test.
- Action: Create the adapter lazily for each serving process, reset inherited state and locks after fork, and test requests after both cold and warmed parent processes fork workers. Keep live hosting verification separate from isolated interpreter checks.
- Evidence: The previous adapter hung in a real fork reproduction. The cold/warm worker regression exercises the corrected Passenger entry point with an alarm that detects a hung request.

## LESSON-013 — Outlined vector lettering is not searchable text

- Category: Drawing extraction
- Status: Adopted
- Lesson: The supplied reviewed 1010 PDF contains thousands of vector paths but almost no searchable engineering text. A page with no extracted characters is not necessarily a raster scan.
- Action: Inspect vectors, images and searchable-character counts separately. Preserve the original, flag recognition gaps and test the real file without inventing node, material or dimension outputs.
- Evidence: `fixtures/1010/README.md`; `tests/integration/test_real_1010.py`; `tests/e2e/real_drawing.py`.

## LESSON-014 — Diagnostic detail needs correlation and a defined capture schema

- Category: Operations
- Status: Adopted
- Lesson: An isolated error message cannot connect a browser action with PDF parsing, project changes and update rollback. Raw payload logging can expose credentials or engineering data.
- Action: Use server-generated request IDs, project IDs, timed phases and safe stack coordinates. Provide searchable administrator logs and exportable structured diagnostics, with bounded retention and metadata-only browser capture.
- Evidence: `docs/LOGGING.md`; `tests/integration/test_diagnostics.py`; Logs browser workflow and privacy checks.

## LESSON-015 — Review notes must not require invented engineering points

- Category: Browser workflow
- Status: Adopted
- Lesson: Both the browser and API blocked notes-only PDF export until a physical node existed. The real drawing regression exposed this unnecessary requirement.
- Action: Enable review export when source sheets exist. Keep empty or unverified engineering models explicit, and test upload, notes and export without adding fabricated points.
- Evidence: `tests/e2e/real_drawing.py` exports the actual reviewed 1010 PDF with saved notes and zero engineering nodes.

## LESSON-016 — Automatic proposals must survive rollback as unverified

- Category: Engineering integrity
- Status: Adopted
- Lesson: A new application's review flag may be invisible to an older release after rollback. Storing a proposed station as an accepted numeric station could then make it look verified.
- Action: Keep canonical stations null until acceptance and store proposed values separately. Generate explicit review exceptions and retain original evidence through cached refreshes.
- Evidence: Pipeline and workbook regressions check blank accepted stations and separate source proposals.

## LESSON-017 — Worker completion must be tied to a current lease and revision

- Category: Automation
- Status: Adopted
- Lesson: A timed-out, cancelled or duplicate worker can finish later and overwrite newer engineer edits unless publication proves ownership.
- Action: Use durable leases, fencing tokens, revision checks, unique artifact keys and a transactional correction outbox. Wait for active drawing work before swapping application code.
- Evidence: Expired-lease, cancellation-during-export, retained-edit and updater-worker-lock regressions.

## LESSON-018 — Pipe length is not a component count

- Category: Source quantities
- Status: Adopted
- Lesson: A material row such as 44.9 m of pipe must not be rounded to 44 or 45 instances. OCR without a proved unit cannot settle that distinction.
- Action: Retain raw source quantities, separate count and length units, and leave unresolved counts blank. Require evidence when correcting quantities.
- Evidence: `test_pipe_length_quantity_is_not_coerced_to_component_count`; the website Components sheet and exported workbook retain source values separately.

## LESSON-019 — A working Excel file is different from a native CAESAR model

- Category: Interchange
- Status: Adopted
- Lesson: Renaming a spreadsheet or guessing a neutral format cannot establish direct CAESAR compatibility.
- Action: Provide editable XLSX and CSV, implement the published versioned CII contract only for supported complete inputs, block unsupported components and keep actual application import qualification visible.
- Evidence: `docs/CAESAR_FORMATS.md`; independent fixed-field tests; conditional native export controls in Excel results.

## LESSON-020 — A readiness gate must count every active element

- Category: Validation
- Status: Adopted
- Lesson: Checking only entered element rows can report completion when other active model edges have no data.
- Action: Derive expected elements from the full topology, compare all required fields and test partial coverage explicitly. Use the same server-side table projection for website, Excel and CSV outputs.
- Evidence: The one-of-three element regression remains incomplete; browser tests inspect the actual numeric workbook and CSV downloads.

## LESSON-021 — Ship account recovery tools with the installed system

- Category: Hosting
- Status: Adopted
- Lesson: The recovery helper existed in GitHub but was omitted from the hosting ZIP, forcing an unnecessary download before a local password reset.
- Action: Include the helper and recovery guide in the private application package. Support a direct local command without network access, and keep the helper unavailable through public web routes.
- Evidence: Release 0.4.1 package regression requires the recovery files and verifies the script's HTTP path returns 404; the recovery implementation uses only local standard-library operations.

## LESSON-022 — Maintenance mode must permit the updater's own checks

- Category: Operations
- Status: Adopted
- Lesson: The updater successfully started a new API, but maintenance mode blocked its frontend check and caused rollback of an otherwise available release.
- Action: Permit read-only public frontend and asset requests during maintenance while keeping project requests blocked. Test the real health-check function against the maintenance-enabled application, including subdirectory hosting.
- Evidence: Release 0.4.2 regression covers both application mounts and proves project actions still return 503.

## LESSON-023 — A completed draft can still lack OCR

- Category: Drawing extraction
- Status: Adopted
- Lesson: The live cPanel worker completed the pipeline but had no OCR engine, producing a legitimate review draft with zero material proposals. Completion alone did not establish successful text recognition.
- Action: Display OCR availability and coverage, provide an operator-triggered account-local engine setup, preserve OCR confidence, and explicitly re-extract after installation instead of reusing empty evidence.
- Evidence: The live reviewed-1010 test reported OCR_UNAVAILABLE on both pages. Release 0.4.3 adds hash-checked optional runtime setup, setup failure/path tests and extraction refresh regression coverage.

## LESSON-024 — Re-extraction needs a current publication checkpoint

- Category: Automation
- Status: Adopted
- Lesson: Re-reading an already registered source retained its sheets but left the new run's expected project revision unset. OCR completed, then publication was rejected as a stale revision even though the project had not changed.
- Action: Record the current revision when registration resumes an active source. Require the re-extraction regression to reach DONE and produce an artifact, rather than merely checking parser calls and retained sheet IDs.
- Evidence: The cPanel OCR test retained both pages' evidence and published it through a cached refresh; release 0.4.4 fixes the initial checkpoint and strengthens its regression.

## LESSON-025 — A local function profile is not a provider deployment

- Category: Serverless validation
- Status: Adopted
- Lesson: A function can fit package and memory limits locally without proving the provider runtime, account permissions, cold starts or actual billing.
- Action: Separate local ZIP/container qualification from an authenticated provider smoke test. Preserve source hashes, confidence and explicit execution profiles; never label a provider function as the local no-network sandbox.
- Evidence: The Functions demo records local qualification separately from live provider results and keeps private website transport outside its small-file demo scope.

## LESSON-026 — Connect providers without exposing their credentials

- Category: Administration and diagnostics
- Status: Adopted
- Lesson: A provider token belongs in private server storage. Returning it to an admin form, validation response, parser environment or troubleshooting log unnecessarily expands its exposure.
- Action: Test before saving, retain a working credential on failed replacement, restrict access to the hosting operator, reject credential-bearing redirects, and record bounded job stages instead of secret-bearing request bodies. An ambiguous submission must stop rather than bill a silent duplicate.
- Evidence: Release 0.4.5 adds the admin connection, separate demo runner, browser checks and API regressions covering credential privacy, permissions, deployment/result contracts and editable exports.

## LESSON-027 — Test the provider's empty and summary responses

- Category: Provider integration
- Status: Adopted
- Lesson: DigitalOcean returns a null namespace list for an empty account and blank deployment credentials in list summaries. A successful action upload also echoes its full binary code. Simplified API fixtures missed all three behaviours.
- Action: Accept a present null list as empty, fetch full namespace details before deployment, and acknowledge a successful action upload without buffering its large echo. Record HTTP status, safe response types, duration and provider request IDs; never record credentials or document contents.
- Evidence: Release 0.4.6 adds these live-observed contracts and regression coverage. The private Sydney function successfully processed the actual 1010 drawing's first page during provider qualification.

## LESSON-028 — Published workbook dimensions and bore fields need explicit handling

- Category: Catalog ingestion
- Status: Adopted
- Lesson: The supplied Numbers-compatible flange workbook omits worksheet dimension tags. Treating unknown dimensions as one column or one row silently loses valid data. API bore also cannot be stored as pipe NPS.
- Action: Prepare all four known-schema sheets using bounded row iteration, retain cached published numbers and raw source fields, keep API bore separate from unknown pipe NPS, and expose missing facing/quality limitations. Dataset preparation never creates a human engineering approval.
- Evidence: Release 0.4.7 prepares 627 source rows with no mapping errors, tests missing-dimension workbooks and preserves the original private source hash.

## LESSON-029 — Backend page jobs must preserve the document experience

- Category: Processing and review
- Status: Adopted
- Lesson: Processing one page per invocation still exceeds platform caps if every invocation carries the entire PDF or large evidence is returned inline. Splitting must also preserve source identity, page transforms and edits.
- Action: Transfer true single-page files with expiring scoped grants, deliver bounded evidence by callback, limit concurrency and submissions across projects, and expose completed observations in the existing workspace. Retain accepted pages during retry and keep partial drafts visibly incomplete.
- Evidence: Release 0.5.0 regression coverage exercises out-of-order delivery, early review/edits, original source integrity, idempotent results, cancellation, failed-page retry, expansion limits and shared budgets. Provider-local qualification remains distinct from live transport qualification.

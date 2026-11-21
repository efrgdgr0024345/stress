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

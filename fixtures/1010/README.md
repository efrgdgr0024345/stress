# User-supplied reviewed 1010 drawing

**Original golden regression: BLOCKED.** See the [asset inventory and restoration
contract](../../docs/GOLDEN_1010_RESTORE.md) and [trusted-pin manifest](golden-manifest.json).
The original generator, original PDF, three JSON blueprints, golden output PDFs
and canonical valve workbook remain missing. Their expected SHA-256 values have
not been supplied. The separate CI golden gate deliberately fails until the
required source evidence and actual regression outputs are available.
The [current CII checklist](../../docs/CII_READINESS_CHECKLIST.md) records native
download requirements and the next bend → tee → rigid/support milestones.

[Download 1010 Reviewed.pdf](1010%20Reviewed.pdf) and upload it through **New
project** in the website. Suggested line identity, to be checked by the engineer:
`8-PG-JE3LN2-1010-FUTURE`.

The user explicitly supplied this file for GitHub publication and real drawing
software testing. It is retained byte-for-byte; SHA-256:

```text
7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59
```

Size: 589,154 bytes. Two unencrypted pages, each approximately 2590.866 ×
1729.133 PDF points, rotation 0. Page 1 has one native annotation, 4,935 vector
paths and 72 searchable characters (review-note text). Page 2 has two native
annotations, 6,526 vector paths and no searchable characters. Neither page has
embedded raster images. Most engineering lettering is outlined vector geometry;
a searchable-text parser cannot recover the printed engineering labels.

This reviewed file is distinct from the plan's missing `1010_original.pdf` and
authoritative engineering model/golden outputs. Reviewer comments inside the
document are drawing data, not instructions to execute code or change models.
Software tests add clearly labelled provisional test graphics in disposable
projects. They do not assert the drawing has been engineered or approved.

See [validation evidence](../../docs/REAL_DRAWING_VALIDATION.md). This fixture
is committed to GitHub but deliberately omitted from the application deployment
ZIP and from production databases; an app update does not insert test projects.

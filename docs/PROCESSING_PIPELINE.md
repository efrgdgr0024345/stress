# Automatic processing pilot

The web/API accepts an authenticated raw PDF, hashes it into private quarantine,
enqueues a durable run and returns HTTP 202. Heavy document parsing does not run
inside that new intake request. The legacy `/sources` API remains a synchronous
compatibility path; the website uses `/intake`.

## User workflow

1. Create a project and select a PDF, or use **Add drawings**.
2. The drawing appears after registration. **Project flow** shows registration,
   page extraction, engineering proposal preparation and native draft generation.
3. Review source issues and the original sheets. **Choose source route** allows
   selecting the main route's start/end from detected graphical linework. Only
   supported connected trees/simple branches are proposed; missing connections,
   disconnected linework and nested branches remain review items.
4. Inspect source-derived station proposals in the point inspector. **Use source
   proposal** fills the draft input; saving with checked evidence accepts it.
   Until then canonical stations are null/blue, including after code rollback.
5. Open **Excel results** for formatted node/element/support/component/exception
   tables. Enter verified element geometry/properties where needed. Saving a
   correction refreshes the review issue from cached evidence automatically.
6. Preview the PDF or export the Excel workbook/review ZIP. A finished job is an
   engineering-review draft, never automatic engineering approval.

The Results page also exports CSV tables and a conditional native CAESAR II
15.1 straight-pipe `.cii` candidate. Missing geometry/properties and unsupported
components block the native file; [the format contract](CAESAR_FORMATS.md)
records application qualification still required.

**Upload revision** explicitly replaces one active PDF. Other documents remain
active. Unique unchanged pages retain IDs based on identical content streams;
changed pages receive new identities and archive previous points/notes for
reconciliation. Originals and prior exports remain downloadable. The bundle
contains a revision report; no proximity-only identity transfer is performed.

## Local worker

```bash
docker build -f worker.Dockerfile -t caesar-worker:local .
./scripts/start.sh
```

Start runs separate web and worker processes. It does not put a scheduler or OCR
thread inside Passenger/FastAPI startup. The parser container gets a single job
directory, read-only source modules, no website secrets, no network, read-only
root, no capabilities, one CPU, bounded memory and a process limit. A Linux
Landlock/seccomp adapter is available when supported; unavailable isolation
produces `WAITING_WORKER` rather than silently removing protections.

On a trusted access-restricted development pilot, the explicit
`CAESAR_PIPELINE_ALLOW_BOUNDED=1` setting allows resource-limited same-account
subprocesses with sanitized environments. That adapter is not a filesystem
sandbox. Tesseract must already be installed for OCR. When missing, the source
and native evidence are retained and `OCR_UNAVAILABLE` is reported; no material
rows or physical facts are invented to hide the gap.

## Existing cPanel hosting

Install the current release through **System updates**. The existing updater's
five-minute cron can also advance drawing jobs; a dedicated one-minute schedule
is available for lower wait times. In **Project flow**, the hosting administrator
can choose the worker mode and **Enable processing**. Only the hosting operator
can change this setting. Bounded hosting mode is an explicit pilot decision.

Equivalent account-level terminal setup:

```bash
/home/learning/virtualenv/caesar-system/3.12/bin/python \
  /home/learning/caesar-system/scripts/enable_pipeline.py --bounded-pilot
```

No root or Node.js is required there. If crontab is unavailable the helper prints
the schedule for cPanel Cron Jobs. Existing unrelated schedules are retained.
Allow the next cron tick, then check Project flow and Logs. A missing OCR binary
or unavailable isolation is a capability gap, not a successful OCR deployment.
GitHub publication alone does not authenticate to or change the hosting account.

DigitalOcean research still favors short scheduled container work over an idle
VM. The local container adapter is tested; a paid remote service/cross-host API
adapter has not been provisioned or qualified by this release.

## Durable contracts

Jobs, progress, attempts and correction outbox rows are additive tables in the
existing private workspace database. Input/options/revision uniqueness prevents
duplicate logical runs. Transactions claim leases and increment fencing tokens;
stale/cancelled attempts cannot commit project results or new artifacts. Projects
serialize active jobs; independent projects can proceed separately. Expired
leases recover after a worker crash. Page checkpoints survive process exit.

Source metadata/project revisions commit together. File staging uses private
attempt paths and atomic renames; unused upload copies and failed staged exports
are removed. Crash-orphan reconciliation/retention beyond those paths remains
an operations task; do not delete referenced originals or artifacts manually.

A manual change writes an outbox record in the same transaction. The runner
reuses immutable extraction evidence, retains reviewed objects/tombstones, pins
catalog versions, recomputes dependent results and emits a new draft. A changed
project version supersedes an older publication instead of losing user edits.

Exact station solving applies only to explicit source POINT/ROUTE/ORDER/STATION
and DIM statements in the qualified native semantic profile. Generic source
vectors define presentation candidates only. Intersecting strokes are not
automatically tees, a longest route is not automatically the main, and paper
distance never becomes mm. Contradictory/underdetermined constraints retain nulls.

Bundle outputs include the native PDF, formatted `engineering-workbook.xlsx`,
project/node/material data, exception list, source/catalog manifests, extraction
evidence, automation coverage and revision report. Workbook and PDF reopening
checks precede publication. Prior revisions/artifacts are not overwritten.

See [scope additions](../PLAN_ADDITIONS_FOR_REVIEW.md) for concrete pilot limits
and [original-plan alignment](PLAN_ALIGNMENT.md) for uncompleted original gates.

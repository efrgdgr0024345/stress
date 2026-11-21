# Automation implementation backlog

Status: proposed work; no ticket below is marked implemented by this document.
Read [the full pipeline plan](AUTOMATED_PROJECT_PIPELINE.md) for original-PDF
page references, invariants, security and release contracts. Preserve existing
manual editing, catalog snapshots, numbering and native export through adapters.

## First deliverable

Build one complete unattended native/vector drawing path from upload through
review-draft export. Do not stop at an OCR demonstration or a queued-upload
screen. Use labelled synthetic and unrelated real drawing fixtures; the missing
1010/canonical assets remain separate, unrun acceptance gates.

| Ticket | Work / suggested location | Depends on | Acceptance |
| --- | --- | --- | --- |
| AUTO-001 | Typed evidence, component-port/physical-point identities, source/sheet revisions and active issue sets; engineering models + migrations | Existing domain | Distinct engineering/presentation/object types; immutable snapshots; partial packs preserve omitted sheets; unknown remains null |
| AUTO-002 | Persistent pipeline/stage/attempt/outbox records and database unique keys; API + new orchestration service | 001 | One logical run for duplicates; concurrent claims and stale workers cannot publish conflicting artifacts |
| AUTO-003 | Intake authentication before parsing, aggregate limits/rates/quotas, quarantine, safe PDF/XLSX/ZIP handling | 001 | Unauthorized/oversized/bomb input is stopped before expensive parsing; originals remain private and immutable |
| AUTO-004 | Scoped worker claim/heartbeat/completion and isolated execution adapter; new worker service | 002–003 | Web worker recycle loses no job; parser cannot read app secrets/network; failures/timeouts release leases; malformed output rejected |
| AUTO-005 | Native spans, text boxes, vector paths, image regions and page transforms; PDF extraction adapter | 001, 004 | Every page accounted for; native/rotation/CropBox fixtures retain correct evidence coordinates |
| AUTO-006 | Title block, full line ID, printed sheet/revision, north and continuation-reference proposals | 005 | Mixed/reordered line packs register correctly or show an explicit evidence-linked conflict |
| AUTO-007 | Materials table parsing, callouts and located component-instance reconciliation | 005–006 | Every source row/quantity accounted for; missing/excess/duplicate/ambiguous/unreadable/size/unlocated exceptions exercised |
| AUTO-008 | Port/centreline graph proposals and main/branch selection; graph engine | 005, 007 | Crossings/junctions and shared interfaces are distinguished; unsupported graph classes remain reviewable |
| AUTO-009 | Exact dimension constraints, signed coordinates, along-route stations and elbow convention | 008 | Sufficient constraints solve exactly; underdetermination/conflicts retain evidence and nulls; no pixel-derived physical lengths |
| AUTO-010 | Continuation candidates, coordinate deltas and proved identity unification | 006, 008–009 | Shared point repeats across sheets; ≥25.4 mm axis discrepancies remain provisional; missing mates are not invented |
| AUTO-011 | Component-specific physical-node proposals, interface reuse and extended numbering/support rules | 007–010 | Flange face/opposite dot, tee, COD, supports, valve/instrument ports and PIT rules pass; ≤152.4 mm downstream support is blue; returning-line/shared-line namespaces survive reruns |
| AUTO-012 | Batch catalog specification extraction, exact proposals and pinned evidence | 007 + approved dataset | No nearest-row substitution; unknown DBB/actuator/vendor values stay explicit; approved dataset changes require project adoption |
| AUTO-013 | Source exclusion regions, bubble/leader/schedule/triad placement and collision solving | 005, 011–012 | No source dimension/title/NORTH obstruction; graphics moves do not change physical stations; unresolved layout issues visible |
| AUTO-014 | Native draft/export/QA jobs and artifact publication; extend existing PDF service | 002, 004, 011–013 | One upload produces a complete traceable draft; all required native objects and original streams verified; no partial publication |
| AUTO-015 | Exception-only review UI and dependency-aware correction/rerun | 001–002, proposal stages | Safe work continues past ambiguities; a correction updates affected stages without erasing accepted edits |
| AUTO-016 | Revised-sheet/entity matching, annotation/override rebase and change reports | 001, 005–011, 015 | Reorder/rotate/add/delete/change/partial-pack cases retain justified identities; superseded sheets excluded; conflicts/stale approvals explicit |
| AUTO-017 | External native-PDF edit import, manifest correspondence and trust checks | 014, 016 | Graphic-only edits rebase; changed node text/source content triggers validation; forged or cross-project IDs confer no approval |
| AUTO-018 | Independent drawing approvals, exact-artifact release and catalog/drawing authority separation | 014–016 | Critical unresolved evidence blocks verified issue; known blue engineering conditions classified correctly; final digests bind approval |
| AUTO-019 | OCR/stroke text and additional qualified drawing profiles | 004–007 + first vertical slice | Labelled coverage/accuracy measured on unrelated drawings; no unseen-template anchor reuse; unreadable regions never silently omitted |
| AUTO-020 | Benchmark/editor qualification, worker fault recovery, observability, backup restore and production adapters | Across stages | Complete corpus report; native round trips across supported editors; failed/stale/duplicate jobs harmless; restored approved artifacts match hashes |

AUTO-012 runs alongside AUTO-008 onward. Only applicable, proved component
dimensions enter AUTO-009; reference catalog values cannot silently constrain
installed geometry. AUTO-001 supplies revision contracts before any regeneration;
AUTO-016 adds correspondence algorithms once extracted entities are meaningful.
AUTO-019 broadens coverage after the first end-to-end path works.

The first vertical slice needs AUTO-001–015 with deliberately bounded drawing
profiles. Broader profiles, complex network policies, revision roundtrips and
verified release require their remaining tickets; a bounded slice must not be
advertised as arbitrary-PDF recognition. Security work starts with intake and
isolated execution, not after recognition is finished.

## Test and rollout policy

- Retain the current API/domain/browser checks, including the real cold/warm
  WSGI fork regression and `/stress/` hosting behavior.
- Add fixture-level evidence/engineering expectations before training/tuning
  recognizers. Separate synthetic, real labelled and unavailable legacy suites.
- Qualify each profile using a versioned policy; publish failures and review
  workload along with successful straight-through runs. Set numeric recognition
  and runtime targets only after a representative benchmark/capacity baseline.
- Exercise crashes, duplicate/out-of-order delivery, expired leases, concurrent
  edits, cancelled/superseded runs, storage failures and approval invalidation.
- Enable automation per project behind a feature flag. Compare proposed output
  with accepted manual results before enabling unattended draft generation.
- Roll out through a restricted pilot. No new worker service, paid account,
  third-party drawing processor or production release is provisioned by this
  backlog; hosting/data-policy/licensing decisions remain explicit prerequisites.

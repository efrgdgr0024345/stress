# Current CII gate and next component milestones

This checklist describes `packages/workbooks/caesar_neutral.py` release 0.6.2.
It does not extend that writer or qualify a desktop application. XLSX/CSV remain
engineering-review handoffs; native CII remains an import candidate only.

## Exact current straight-pipe download requirements

| Check | Required behavior |
| --- | --- |
| Topology | At least one route edge; every point connected; degree at most two; no direction change or reversal at intermediate points. Branch auxiliaries are unsupported. |
| Component coverage | Node kind `endpoint` only. Any prepared physical component occurrence blocks this straight-pipe profile, even if ports are mapped. |
| Station evidence | Every point has an accepted station and nonempty source evidence; no `verification: proposed` points. |
| Signed geometry | Every topology edge has explicit DX/DY/DZ; nonzero straight length agrees with accepted along-route station difference within 0.01 mm. Page XY is never used. |
| Constraints | No conflicting/stale dimensional source or stale accepted vector solution. |
| Origin | Explicitly confirm the first ordered main point as the local model origin. This does not claim a surveyed origin. |
| Settings | Piping code ID 1–999; vertical axis Y or Z; finite ambient temperature between −273.15 and 2000 °C. |
| Numbers and labels | Unique node numbers 1–9,999,999; Windows-1252 labels without control characters and within documented field widths. |
| Pipe geometry | Positive OD, positive wall, twice wall below OD; corrosion nonnegative and below wall. |
| Operating input | Temperature at least −273.15 °C; nonnegative pressure. |
| Material input | Material ID 1–699; positive cold/hot modulus and allowables; Poisson ratio strictly between 0 and 0.5. |
| Mass/insulation | Positive pipe density; nonnegative fluid density and insulation thickness. Positive insulation thickness requires a finite nonnegative insulation density. Explicit dry/uninsulated declarations may be zero; missing values remain unknown. |
| Numeric range | Required values finite with absolute value at most 10¹²; supplied insulation density finite in 0–10¹². |
| Serialization | Decimal unit conversion to declared English units; fixed-width output rejects length rounding above 0.01 mm or field overflow. |

Each edge requires these current `REQUIRED` keys:

```text
dx_mm dy_mm dz_mm od_mm wall_mm corrosion_mm material_code
temperature_c pressure_mpa elastic_modulus_mpa hot_modulus_mpa
poisson_ratio pipe_density_kg_m3 fluid_density_kg_m3
insulation_thickness_mm cold_allowable_mpa hot_allowable_mpa
```

`insulation_density_kg_m3` is conditional as described above. An absent required
value blocks native output; unused native control slots do not establish an
engineering value. The returned `available` flag means a bounded candidate can
be serialized, not that CAESAR accepted it. `qualified_application_roundtrip`
remains **false**, and `status` remains `IMPORT_CANDIDATE_ONLY`.

## First three component milestones after straight pipe

Implement only after original Phase A is green, in the requested order:

1. **Bends:** source-proved theoretical COD and dimension convention, bend plane,
   radius/angle, tangent connectivity, thickness/material and supported bend/SIF
   auxiliaries. Fully constrained engineering geometry is required; no radius,
   angle or station is inferred from a paper bend. Exercise BEND counts/pointers
   and an actual 15.1 conversion/reopen report before qualifying this profile.
2. **Tees:** one main-run common intersection UUID, correct main/branch element
   connectivity, sizes/thicknesses, tee type, applicable SIF and flexibility data
   with evidence. Exercise SIF&TEES records, branch numbering and native
   pointers/counts. An unknown required tee value blocks the candidate.
3. **Valve rigids and supports:** explicit process ends and proved face-to-face
   length, shared adjacent flange interfaces, vendor/reference status, known
   weight and declared scope; explicit support restraint type, direction,
   stiffness/gaps/friction where required by its supported type. Exercise RIGID
   and RESTRANT records without turning a missing value into zero. Unknown DBB
   dimensions/weight remain N/A and block a native model needing those values.

Flange-specific auxiliaries, reducers and the remaining component types follow
as separate evidenced profiles. The third milestone groups rigid/support
records because that is the supplied order; it does not assume one contract
covers both objects or permits component omissions.

Every component milestone needs exact vendor field/pointer validation plus a
licensed CAESAR II 15.1 import → inspect → save → close → reopen comparison of
all node/element counts, signed coordinates, component/operating properties,
units, code/material IDs and converter diagnostics. Store input/output hashes,
application build, operator, date and comparison tolerances in the report. No
real desktop round trip has been run; no result or licence decision is invented.

## Complete Excel/CSV topology (LESSON-020)

Table rows must come from **every** edge of `topology(project['nodes'])`,
including branch takeoffs and unsupported component types. Missing signed
geometry/property cells remain blank. Blocking a native candidate must not drop
those rows from the review workbook or CSV. The mixed-component/unknown-geometry
regression in `tests/unit/test_component_plan_contract.py` checks this contract
independently of native-profile readiness.

# Three engineering output formats

The requested two or three useful output types are **XLSX**, **CSV** and native
**CAESAR II neutral CII**. These are different handoffs, not a market-share
ranking or three interchangeable CAESAR model formats.

| Website control | Output | Current use |
| --- | --- | --- |
| Export Excel | Editable `.xlsx` with styled tables, numeric cells, evidence, exceptions and exact decimal text | Main engineering review deliverable; no macro/connector needed |
| CSV tables | ZIP of UTF-8 BOM CSV sheets and revision manifest | Plain data interchange; literal text is protected against spreadsheet formula injection |
| CAESAR neutral | Windows-1252 `.cii`, profile `caesar-15.1-straight-pipe-v1` | Conditional native import candidate for the documented CAESAR II 15.1 interface |

Both table formats work independently of the installed CAESAR version. An XLSX
workbook or CSV file is not labelled a native stress model. The native option
uses the vendor's published format, not a renamed spreadsheet or an NTXT report.

## Bounded native profile

Native output requires accepted point stations/evidence, one connected straight
pipe route, unique node numbers, signed DX/DY/DZ, OD/wall/corrosion, material ID,
one temperature/pressure condition, cold/hot moduli and allowables, Poisson ratio,
pipe/fluid densities and an explicit insulation declaration. Insulated pipe also
requires insulation density. Settings declare piping-code ID, ambient temperature,
vertical axis and a local origin at the first main point. That local frame is
explicitly chosen; it is not a claim of surveyed coordinates.

Signed geometry must agree with accepted straight-pipe station differences to
0.01 mm. Drawing pixels never provide physical lengths. Intermediate direction
changes, bends, tees, supports, valves, rigids and other component types require
additional component-specific auxiliaries and currently block this profile.
Unknown engineering fields block native download rather than being filled with
zero. Explicit zero fluid density means dry pipe; zero insulation thickness
means uninsulated pipe. Documented unused-feature/control slots are emitted as
absent/default slots, not substitutes for unknown required properties.

The file declares English units. Canonical mm/MPa/Celsius/kg-per-cubic-metre
values are converted with Decimal arithmetic. Fixed-width serialization rejects
length rounding above 0.01 mm, invalid labels and unsupported field sizes.
Independent structural tests check section counts, field offsets, units and
known synthetic geometry. The native API and automatic review bundle include a
readiness/status report; incomplete real drawings have no fabricated CII file.

**A real CAESAR II import has not been run in this Linux environment.** Every
native response remains `IMPORT_CANDIDATE_ONLY` with
`qualified_application_roundtrip: false`. Use CAESAR's neutral-file converter,
then compare node/element counts, coordinates, properties and diagnostics with
the workbook before engineering use. Full component profiles, stress analysis
and verified-for-modelling approval remain open work. Unsupported software
versions need a separately tested profile; changing the version label is unsafe.

## Official format contract

Consulted 22 November 2026. Hexagon's CAESAR II Users Guide 15.1 documents the
ASCII neutral interface and warns that the format can change between versions:

- [Neutral file overview](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337037)
- [Version and 60-line title block](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337038)
- [Control counts and vertical-axis flag](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337039)
- [Basic element fields and auxiliary pointers](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337040)
- [Auxiliary records and allowables](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337041)
- [Miscellaneous material IDs and execution settings](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/1532581)
- [Unit conversions and labels](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337060)
- [Optional nodal coordinates](https://docs.hexagonppm.com/r/en-US/CAESAR-II-Users-Guide/15.1/337061)

Implementation: `packages/workbooks/caesar_neutral.py`. No third-party converter
program, proprietary CAESAR executable or undocumented binary C2 writer is bundled.

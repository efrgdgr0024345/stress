# Canonical flange workbook

The user-supplied `PIPE100_Flange_Weights_B16_5_B16_47_API6A_Numbers.xlsx`
is stored privately as a catalog source, not embedded in public website assets
or the public GitHub repository. Source SHA-256:
`84cc71a66c2f47a3e70f27adf7c286cd346fdf722d5dfcf50158085d2e2d356a`.

| Sheet | Records |
| --- | ---: |
| B16.5 | 348 |
| B16.47 Series A | 132 |
| B16.47 Series B | 108 |
| API 6A | 39 |

The adapter retains cached published values, units, bolting allowances, sheet/
row identity, source URLs, quality and all original row fields. No formulas or
macros are executed. Published half/full bolting values are checked against the
source bare weight, all-stud weight and per-nut count, without double addition.
All four datasets start pending human approval. They are searchable/paginated in
the existing catalog page and retain their source provenance after approval.

The API sheet supplies true bore, not pipe NPS. Facing is not a source column;
it remains UNSPECIFIED. Estimated/approximate geometry is labelled accordingly.
These unknowns cannot silently become an exact project component match.
The 1010 API rows reproduce the source's approximately 1232.5 / 1459.7 / 1686.8 N
and 99.1 / 117.2 / 135.3 N bare/half/full values, as preliminary source values.
Actual manufacturer confirmation and final engineering acceptance are separate.

Ordinary XLSX mapping remains available. The known adapter handles all four
sheets and is idempotent for the same source/record hashes. The original file
stays immutable; preparing mappings does not sign a person's engineering review.

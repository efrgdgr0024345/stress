"""Reviewed workbook mappings and exact matching. No near-match substitutions."""

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re

TEXT_FIELDS = [
    "family",
    "standard",
    "rating",
    "nps",
    "api_bore",
    "component_type",
    "facing",
    "end_connection",
    "code",
    "vendor",
    "model",
    "source",
    "quality",
    "weight_scope",
    "operator_scope",
    "material",
]
WEIGHT_FIELDS = [
    "weight_n",
    "half_weight_n",
    "full_weight_n",
    "studs_weight_n",
    "nut_weight_n",
]
LENGTH_FIELDS = ["length_mm", "stud_length_mm"]
FIELDS = TEXT_FIELDS + WEIGHT_FIELDS + LENGTH_FIELDS + ["stud_count"]
MATCH_FIELDS = [
    "family",
    "standard",
    "rating",
    "nps",
    "api_bore",
    "component_type",
    "facing",
    "end_connection",
    "code",
    "vendor",
    "model",
]
REQUIRED = [
    "family",
    "standard",
    "rating",
    "nps",
    "component_type",
    "source",
    "quality",
]
QUALITY = ["REFERENCE_ONLY", "ESTIMATED", "MANUFACTURER_CONFIRMED"]


def normal(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def match_value(field,value):
    text=normal(value)
    if field in ('nps','api_bore'):
        number=re.sub(r'\s*(?:in|inch|inches|["″])$','',text).strip()
        number=re.sub(r'(?<=\d)\s*-\s*(?=\d+/\d+$)',' ',number)
        if re.fullmatch(r'\d+(?:\.\d+|/\d+|\s+\d+/\d+)?',number):
            try:return str(sum((Fraction(p) for p in number.split()),Fraction(0)))
            except (ValueError,ZeroDivisionError):pass
    return text


def numeric(value):
    if value is None or str(value).strip().upper() in (
        "",
        "N/A",
        "NA",
        "NONE",
        "UNKNOWN",
        "-",
    ):
        return None
    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {str(value)[:40]}") from exc
    if not number.is_finite() or number < 0 or number > Decimal("1e12"):
        raise ValueError("Numeric values must be finite, nonnegative and below 1e12.")
    return number


def normalize_record(raw):
    record = {key: str(raw.get(key) or "").strip() for key in TEXT_FIELDS}
    record["family"] = normal(record["family"])
    record["quality"] = record["quality"].upper()
    for key in REQUIRED:
        if key == 'nps' and 'api 6a' in normal(record['standard']) and record.get('api_bore'):
            continue
        if not record[key]:
            raise ValueError(f"Missing required field: {key}")
    if record["family"] not in ("flange", "valve"):
        raise ValueError("family must be flange or valve.")
    if record["quality"] not in QUALITY:
        raise ValueError(
            "quality must be REFERENCE_ONLY, ESTIMATED or MANUFACTURER_CONFIRMED."
        )
    keys = ["facing"] if record["family"] == "flange" else ["end_connection"]
    if "api 6a" in normal(record["standard"]):
        keys.append("api_bore")
    if record["quality"] == "MANUFACTURER_CONFIRMED":
        keys += ["vendor", "model"]
    for key in keys:
        if not record[key]:
            raise ValueError(f"Missing required field: {key}")
    for key in WEIGHT_FIELDS + LENGTH_FIELDS + ["stud_count"]:
        value = numeric(raw.get(key))
        record[key] = str(value) if value is not None else None
    if record["stud_count"] is not None and Decimal(record["stud_count"]) % 1:
        raise ValueError("stud_count must be an integer.")
    record["calculations"] = []
    # Only bare-flange weights may have bolting added. Never add twice to an assembly.
    if (
        record["family"] == "flange"
        and record["weight_scope"].upper() == "BARE_FLANGE"
        and all(
            record.get(key) is not None
            for key in ["weight_n", "studs_weight_n", "nut_weight_n", "stud_count"]
        )
    ):
        bare, studs, nut, count = (
            Decimal(record[key])
            for key in ["weight_n", "studs_weight_n", "nut_weight_n", "stud_count"]
        )
        values = {
            "half_weight_n": bare + studs / 2 + nut * count,
            "full_weight_n": bare + studs + 2 * nut * count,
        }
        for key, value in values.items():
            if record[key] is None:
                record[key] = str(value)
                record["calculations"].append(
                    f'{key}: bare flange + {"half studs + one nut per stud" if key == "half_weight_n" else "all studs + two nuts per stud"}'
                )
            elif abs(Decimal(record[key]) - value) > Decimal("0.1"):
                raise ValueError(
                    f"{key} disagrees with supplied bare-flange / bolting values by more than 0.1 N. Resolve the source discrepancy."
                )
    return record


def map_rows(
    rows, mapping, constants, weight_unit="N", length_unit="mm", source_hash=""
):
    if any(key not in FIELDS for key in set(mapping) | set(constants)):
        raise ValueError("Unrecognized catalog field.")
    if weight_unit not in ("N", "kg", "lbf") or length_unit not in ("mm", "in"):
        raise ValueError("Choose explicit supported weight and length units.")
    factors = {
        "N": Decimal(1),
        "kg": Decimal("9.80665"),
        "lbf": Decimal("4.4482216152605"),
    }
    records, errors = [], []
    for row_number, values in rows:
        if not any(value is not None and str(value).strip() for value in values):
            continue
        raw = {
            key: values[col] if col < len(values) else None
            for key, col in mapping.items()
        }
        raw.update(
            {key: value for key, value in constants.items() if str(value).strip()}
        )
        try:
            for key in WEIGHT_FIELDS:
                number = numeric(raw.get(key))
                raw[key] = (
                    str(number * factors[weight_unit]) if number is not None else None
                )
            for key in LENGTH_FIELDS:
                number = numeric(raw.get(key))
                raw[key] = (
                    str(number * (Decimal("25.4") if length_unit == "in" else 1))
                    if number is not None
                    else None
                )
            record = normalize_record(raw)
            record["source_row"] = row_number
            record["id"] = hashlib.sha256(
                (source_hash + json.dumps(record, sort_keys=True)).encode()
            ).hexdigest()[:24]
            records.append(record)
        except ValueError as exc:
            errors.append({"row": row_number, "message": str(exc)})
    return {
        "records": records,
        "errors": errors,
        "units": {
            "weight_input": weight_unit,
            "length_input": length_unit,
            "weight_output": "N",
            "length_output": "mm",
            "gravity_m_s2": "9.80665" if weight_unit == "kg" else None,
        },
    }


def exact_match(records, spec):
    family = normal(spec.get("family"))
    required = ["family", "standard", "rating", "nps", "component_type"]
    required += ["facing"] if family == "flange" else ["end_connection"]
    if "api 6a" in normal(spec.get("standard")):
        required.append("api_bore")
        required.remove('nps')
    missing = [key for key in required if not normal(spec.get(key))]
    if missing:
        return {"status": "INCOMPLETE_SPEC", "missing": missing, "candidates": []}
    candidates = [
        record
        for record in records
        if all(
            match_value(key,record.get(key)) == match_value(key,spec[key])
            for key in MATCH_FIELDS
            if normal(spec.get(key))
            and not (key == 'nps' and 'api 6a' in normal(spec.get('standard')) and not normal(record.get('nps')))
        )
    ]
    return {
        "status": (
            "NO_EXACT_MATCH"
            if not candidates
            else "AMBIGUOUS_MATCH" if len(candidates) > 1 else "EXACT_MATCH"
        ),
        "missing": [],
        "candidates": candidates[:100],
        "count": len(candidates),
    }


def schedule_lines(materials):
    lines = ["COMPONENT SCHEDULE | ENGINEERING REVIEW"]
    for item in materials:
        match = item.get("catalog_match")
        record = match.get("record", {}) if match else {}

        def value(key):
            return record.get(key) if record.get(key) is not None else "N/A"

        lines.append(
            f"{item['item_no']}  {item['family'].upper()}  {item['size']}  QTY {item['quantity'] if item.get('quantity') is not None else 'N/A'} | L: {value('length_mm')} mm | W: {value('weight_n')} N"
        )
        if match:
            lines.append(
                f"{record.get('standard','')} / {record.get('rating','')} / {record.get('component_type','')} | {match.get('status','REFERENCE_ONLY')}"
            )
            if item["family"] == "flange":
                lines.append(
                    f"W_half: {value('half_weight_n')} N | W_full: {value('full_weight_n')} N | {record.get('weight_scope') or 'SCOPE UNCONFIRMED'}"
                )
            lines.append(
                f"SOURCE: {record.get('source','')} | DATASET {match['catalog_version_id'][:8]} / ROW {record.get('source_row','?')}"
            )
            if item["family"] == "valve":
                lines.append(
                    f"VENDOR: {record.get('vendor') or 'UNCONFIRMED'} / {record.get('model') or 'UNCONFIRMED'} | OPERATOR: {record.get('operator_scope') or 'UNKNOWN'}"
                )
        else:
            lines.append("NO EXACT CATALOG MATCH. UNKNOWN VALUES ARE NOT ZERO.")
    if any(item["family"] == "valve" for item in materials):
        lines += [
            "VALVE DATA MAY BE MANUFACTURER-SPECIFIC OR ESTIMATED.",
            "OBTAIN ACTUAL MANUFACTURER WEIGHTS AND LENGTHS FOR FINAL STRESS ANALYSIS.",
        ]
    return lines

"""Known PIPE100 schema adapter. Workbook text is data, never executable code.

Cached published numbers are retained; formulas/macros are not evaluated.
Unknown pipe NPS and facing stay unknown instead of being invented from bore.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from openpyxl import load_workbook
from packages.catalogs import normalize_record

SOURCE_SHA256 = '84cc71a66c2f47a3e70f27adf7c286cd346fdf722d5dfcf50158085d2e2d356a'
SHEETS = {'B16.5': 'ASME B16.5', 'B16.47 Series A': 'ASME B16.47 Series A',
          'B16.47 Series B': 'ASME B16.47 Series B', 'API 6A': 'API 6A'}
NUMBERS = {'weight_n': 'Flange weight (N)', 'half_weight_n': 'Flange + half studs + 1 nut/stud (N)',
           'full_weight_n': 'Flange + all studs + 2 nuts/stud (N)', 'stud_count': 'Studs (count)',
           'stud_length_mm': 'Stud length (mm)', 'studs_weight_n': 'Studs, full (N)',
           'nut_weight_n': 'Nut weight per nut (N)'}


def prepare(path):
    path = Path(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    result = []
    try:
        if not all(name in book.sheetnames for name in SHEETS):
            raise ValueError('PIPE100_SCHEMA_NOT_RECOGNIZED')
        for name, standard in SHEETS.items():
            sheet = book[name]
            iterator = sheet.iter_rows(values_only=True)
            headers = list(next(iterator))
            required = set(NUMBERS.values()) | {'Flange type', 'Stud data source URL', 'Flange weight source URL', 'Flange weight basis'}
            required |= {'API bore (in)', 'Rating (psi)'} if name == 'API 6A' else {'NPS (in)', 'Class'}
            if not required <= set(headers):
                raise ValueError('PIPE100_SCHEMA_NOT_RECOGNIZED')
            records, errors = [], []
            for index, values in enumerate(iterator, 2):
                if index > 5001:
                    raise ValueError('PIPE100_ROW_LIMIT')
                if not any(v is not None for v in values):
                    continue
                source = dict(zip(headers, values))
                try:
                    basis = str(source.get('Flange weight basis') or '')
                    raw = {'family': 'flange', 'standard': standard,
                           'nps': str(source.get('NPS (in)') or ''),
                           'api_bore': str(source.get('API bore (in)') or ''),
                           'rating': str(source.get('Rating (psi)') or source.get('Class') or ''),
                           'component_type': str(source['Flange type']), 'facing': 'UNSPECIFIED',
                           'quality': 'ESTIMATED' if 'estimat' in basis.lower() or 'approx' in basis.lower() else 'REFERENCE_ONLY',
                           'source': str(source.get('Flange weight source URL') or ''),
                           'weight_scope': 'BARE_FLANGE', 'operator_scope': 'NOT_APPLICABLE',
                           **{key: source[label] for key, label in NUMBERS.items()}}
                    record = normalize_record(raw)
                    # Retain original decimal text/numbers and all source fields.
                    record.update(source_row=index, source_sheet=name, source_sha256=sha,
                                  source_fields={str(k): v for k, v in source.items()},
                                  limitations=['FACING_NOT_SPECIFIED_IN_SOURCE', 'REFERENCE_DATA_REQUIRES_ENGINEERING_ACCEPTANCE'] +
                                  (['PIPE_NPS_NOT_SPECIFIED_IN_SOURCE'] if name == 'API 6A' else []))
                    record['id'] = hashlib.sha256((sha + name + str(index) + json.dumps(record, sort_keys=True)).encode()).hexdigest()[:24]
                    records.append(record)
                except (ValueError, TypeError) as error:
                    errors.append({'row': index, 'message': str(error)[:200]})
            result.append({'sheet': name, 'records': records, 'errors': errors,
                           'units': {'weight_input': 'N', 'length_input': 'mm', 'weight_output': 'N', 'length_output': 'mm'},
                           'source_sha256': sha, 'adapter': 'pipe100-flanges-1',
                           'known_source_hash': sha == SOURCE_SHA256,
                           'status': 'INVALID' if errors or not records else 'PENDING_APPROVAL',
                           'approval': None})
        return result
    finally:
        book.close()

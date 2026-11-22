"""Prepare private known-schema catalog versions without signing them off."""
import hashlib
import json
from fastapi import HTTPException
from packages.catalogs.canonical import prepare


def prepare_source(api, catalog_id, actor):
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator permission required.')
    with api.db() as conn:
        row = conn.execute('SELECT * FROM catalogs WHERE id=? AND tenant=?', (catalog_id, actor['tenant'])).fetchone()
    if not row:
        raise HTTPException(404, 'Catalog not found.')
    path = api.DATA / 'catalogs' / f'{catalog_id}.xlsx'
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise HTTPException(409, 'Catalog source integrity check failed.')
    try:
        prepared = prepare(path)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    result = []
    with api.LOCK, api.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        existing = [{**dict(r), 'data': json.loads(r['data'])} for r in conn.execute(
            'SELECT * FROM catalog_versions WHERE catalog_id=? AND tenant=?', (catalog_id, actor['tenant']))]
        seq = max((r['seq'] for r in existing), default=0)
        for data in prepared:
            digest = hashlib.sha256(json.dumps(data['records'], sort_keys=True).encode()).hexdigest()
            match = next((r for r in existing if r['data'].get('adapter') == data['adapter'] and
                          r['data'].get('records_sha256') == digest), None)
            if match:
                result.append(match)
                continue
            seq += 1
            data.update(source_filename=row['filename'], records_sha256=digest,
                        created_by=actor['name'], mapping={'sheet': data['sheet'], 'adapter': data['adapter']})
            record = {'id': api.uid(), 'tenant': actor['tenant'], 'catalog_id': catalog_id,
                      'seq': seq, 'created': api.now(), 'data': data}
            conn.execute('INSERT INTO catalog_versions VALUES (?,?,?,?,?,?)',
                         (record['id'], actor['tenant'], catalog_id, seq, record['created'], json.dumps(data)))
            result.append(record)
        meta = json.loads(row['data'])
        meta.update(status='PREPARED_FOR_REVIEW', adapter='pipe100-flanges-1')
        for sheet in meta.get('sheets', []):
            data = next((d for d in prepared if d['sheet'] == sheet['name']), None)
            if data:
                sheet['rows'] = len(data['records']) + len(data['errors']) + 1
                sheet['columns'] = 22 if sheet['name'] == 'API 6A' else 20
        conn.execute('UPDATE catalogs SET data=? WHERE id=?', (json.dumps(meta), catalog_id))
        api.audit(conn, 'catalog:' + catalog_id, actor['name'], 'Prepared canonical flange datasets',
                  f'{len(prepared)} sheets; {sum(len(d["records"]) for d in prepared)} rows; human approval pending')
    api.diag.emit(api.DATA, 'catalog.canonical.prepared', catalog_id=catalog_id,
                  datasets=len(result), records=sum(len(d['data']['records']) for d in result))
    return result

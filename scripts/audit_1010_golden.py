"""Read-only audit of the required original assets; unknown pins fail closed."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT=Path(__file__).resolve().parents[1]
ROLES=('legacy_generator','original_pdf','review_project','annotation_blueprint',
       'flange_specs','golden_pdf','valve_workbook')
REVIEWED_SHA='7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'


def safe_file(root,name):
    if not isinstance(name,str):raise ValueError('Authoritative filename not supplied')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not path.parts:
        raise ValueError('Unsafe fixture path')
    target=root.joinpath(*path.parts)
    if any(p.is_symlink() for p in (target,*target.parents)) or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Fixture symlinks/path escapes are forbidden')
    return target


def audit(root=None):
    root=Path(root or ROOT/'fixtures/1010')
    manifest_path=root/'golden-manifest.json'
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('format')!='caesar-1010-golden-manifest-1' or set(manifest.get('assets',{}))!=set(ROLES):
        raise ValueError('Golden manifest must retain every required original asset role')
    rows=[]
    for role in ROLES:
        item=manifest['assets'][role];issues=[];actual=None
        expected=item.get('expected_sha256')
        if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):issues.append('TRUSTED_SHA256_NOT_SUPPLIED')
        if not isinstance(item.get('trusted_hash_source'),str) or not item['trusted_hash_source'].strip():issues.append('TRUSTED_HASH_SOURCE_NOT_SUPPLIED')
        try:
            path=safe_file(root,item.get('path'))
            if not path.is_file():issues.append('FILE_MISSING')
            elif path.stat().st_size>64*1024**2:issues.append('ASSET_SIZE_LIMIT')
            else:
                actual=hashlib.sha256(path.read_bytes()).hexdigest()
                if actual!=expected:issues.append('SHA256_MISMATCH')
                if role=='original_pdf' and actual==REVIEWED_SHA:issues.append('REVIEWED_PDF_IS_NOT_THE_ORIGINAL_FIXTURE')
        except ValueError as error:issues.append(str(error))
        rows.append({'role':role,'path':item.get('path'),'expected_sha256':expected,
                     'actual_sha256':actual,'ready':not issues,'issues':issues})
    return {'format':'caesar-1010-asset-audit-1','status':'READY' if all(r['ready'] for r in rows) else 'BLOCKED',
            'assets':rows,'original_legacy_test_count':13,'legacy_test_root':manifest.get('legacy_test_root'),
            'legacy_tests_restored':False,'engineering_verified':False,
            'reviewed_pdf_is_a_separate_software_fixture':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict',action='store_true',help='Exit nonzero until all original files have trusted pins')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=audit()
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    raise SystemExit(1 if args.strict and result['status']!='READY' else 0)

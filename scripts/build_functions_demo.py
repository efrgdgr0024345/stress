"""Build an allowlisted, hash-pinned Linux/x86_64 Functions demo bundle."""
import argparse
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import shutil
import stat
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.api.ocr_setup import WHEELS,MODEL,download

PYMUPDF=('https://files.pythonhosted.org/packages/2a/6b/3de1714d734ff949be1e90a22375d0598d3540b22ae73eb85c2d7d1f36a9/pymupdf-1.26.7-cp310-abi3-manylinux_2_28_x86_64.whl','69dfc78f206a96e5b3ac22741263ebab945fdf51f0dbe7c5757c3511b23d9d72')


def wheel(url,digest,directory):
    from urllib.request import urlopen
    with urlopen(url,timeout=60) as response:data=response.read(40*1024**2+1)
    if len(data)>40*1024**2 or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Wheel checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(e.file_size for e in archive.infolist())>160*1024**2:raise ValueError('Expanded wheel limit')
        for entry in archive.infolist():
            path=PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Unsafe wheel path')
            target=directory/str(path)
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(entry));target.chmod(0o644)


def build(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new output directory; existing build was retained.')
    function=output/'packages/caesar/extract';function.mkdir(parents=True)
    shutil.copyfile(ROOT/'serverless/digitalocean/project.yml',output/'project.yml')
    for source in (ROOT/'serverless/digitalocean/function').glob('*.py'):shutil.copyfile(source,function/source.name)
    for name in ('__init__.py','extract.py'):
        target=function/'packages/automation'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'packages/automation'/name,target)
    (function/'packages/__init__.py').write_text('')
    wheel(*PYMUPDF,function/'lib');wheel(*WHEELS['x86_64'],function/'lib')
    model=function/'ocr/tessdata/eng.traineddata';model.parent.mkdir(parents=True);model.write_bytes(download(*MODEL))
    package=output/'extract.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for source in sorted(function.rglob('*')):
            if source.is_file():
                if source.is_symlink():raise ValueError('Build contains a symlink')
                entry=zipfile.ZipInfo(source.relative_to(function).as_posix(),date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
                archive.writestr(entry,source.read_bytes(),compresslevel=9)
    size=package.stat().st_size
    if size>48_000_000:raise ValueError(f'Deployment package exceeds conservative 48 MB limit: {size}')
    report={'format':'caesar-functions-build-1','runtime':'python:3.12','architecture':'x86_64','zip_bytes':size,'limit_bytes':48_000_000,'zip_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'dependency_sha256':{'PyMuPDF':PYMUPDF[1],'tesserocr':WHEELS['x86_64'][1],'eng':MODEL[1]},'production_transport':False}
    deployed=output/'deploy/packages/caesar/extract';deployed.mkdir(parents=True)
    shutil.copyfile(ROOT/'serverless/digitalocean/project.yml',output/'deploy/project.yml')
    shutil.copyfile(package,deployed/'extract.zip')
    (output/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return function


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args();build(args.output)

"""Optional account-local OCR runtime. No changes to the website virtualenv.

Only the operator queues installation; the separate runner performs it. Binary
wheels and the language model are immutable downloads checked before loading.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import zipfile

from services.api.updates import read,write

VERSION='tesserocr-2.9.2-eng-fast-87416418'
WHEELS={
 'x86_64':('https://files.pythonhosted.org/packages/3b/e7/ec64396963a4b776935e4fb79dd9be946103f04dfb301941670b3336b44b/tesserocr-2.9.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl','7108fa533940151b3da31ec859426157746797a7b2d7890718ff0a1aa7d6675b'),
 'aarch64':('https://files.pythonhosted.org/packages/bb/c4/edbd60235d04c20fbca6d96098f6e3e2f3db58312a6a327c8064b79f4a3f/tesserocr-2.9.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl','e7b15149a86c57d2208fa6e257a9a909a25bd40c3c9cb4f19b35e8b2630eabea')}
MODEL=('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata','7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2')


def status(data):return read(Path(data)/'pipeline/ocr-setup.json')


def queue(data):
    value=status(data)
    if value.get('state') in ('queued','running','ready'):return value
    value={'state':'queued','version':VERSION,'updated':time.time()}
    write(Path(data)/'pipeline/ocr-setup.json',value)
    return value


def download(url,digest):
    with urlopen(url,timeout=45) as response:content=response.read(16*1024**2+1)
    if len(content)>16*1024**2 or hashlib.sha256(content).hexdigest()!=digest:raise ValueError('OCR_DOWNLOAD_CHECKSUM_FAILED')
    return content


def unpack(content,target):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries=archive.infolist()
        if len(entries)>200 or sum(e.file_size for e in entries)>80*1024**2:raise ValueError('OCR_ARCHIVE_LIMIT')
        seen=set()
        for entry in entries:
            path=PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or not path.parts or path.parts[0] not in ('tesserocr','tesserocr.libs','tesserocr-2.9.2.dist-info') or stat.S_ISLNK(entry.external_attr>>16) or entry.filename in seen:raise ValueError('OCR_ARCHIVE_PATH_REJECTED')
            seen.add(entry.filename);dest=target/str(path)
            if entry.is_dir():dest.mkdir(parents=True,exist_ok=True,mode=0o700);continue
            dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            dest.write_bytes(archive.read(entry));dest.chmod(0o600)


def run_pending(data):
    data=Path(data);previous=status(data);state_file=data/'pipeline/ocr-setup.json'
    if previous.get('state')=='running' and previous.get('updated',0)<time.time()-600:
        write(state_file,{**previous,'state':'failed','error':'OCR_SETUP_INTERRUPTED','updated':time.time()});return False
    if previous.get('state')!='queued':return False
    value={'state':'running','version':VERSION,'updated':time.time()};write(state_file,value)
    try:
        libc,libver=platform.libc_ver()
        if sys.platform!='linux' or sys.version_info[:2]!=(3,12) or platform.machine() not in WHEELS or libc!='glibc' or tuple(int(v) for v in libver.split('.')[:2])<(2,27):raise ValueError('OCR_PLATFORM_UNSUPPORTED')
        destination=data/'pipeline/ocr'
        if destination.is_symlink():raise ValueError('OCR_RUNTIME_PATH_REJECTED')
        with tempfile.TemporaryDirectory(prefix='ocr-install-',dir=state_file.parent) as temporary:
            stage=Path(temporary)/'ocr';runtime=stage/'runtime';model=stage/'tessdata'
            runtime.mkdir(parents=True,mode=0o700);model.mkdir(mode=0o700)
            unpack(download(*WHEELS[platform.machine()]),runtime)
            (model/'eng.traineddata').write_bytes(download(*MODEL));(model/'eng.traineddata').chmod(0o600)
            code="import sys;sys.path.insert(0,sys.argv[1]);import tesserocr;api=tesserocr.PyTessBaseAPI(path=sys.argv[2],lang='eng');api.End()"
            checked=subprocess.run([sys.executable,'-I','-c',code,str(runtime),str(model)],env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'OMP_THREAD_LIMIT':'1'},capture_output=True,timeout=45)
            if checked.returncode:raise ValueError('OCR_RUNTIME_STARTUP_FAILED')
            write(stage/'manifest.json',{'version':VERSION,'wheel_sha256':WHEELS[platform.machine()][1],'model_sha256':MODEL[1]})
            if destination.exists():raise ValueError('OCR_RUNTIME_ALREADY_EXISTS')
            os.replace(stage,destination)
        value.update(state='ready',updated=time.time())
    except Exception as error:
        allowed={'OCR_PLATFORM_UNSUPPORTED','OCR_DOWNLOAD_CHECKSUM_FAILED','OCR_ARCHIVE_LIMIT','OCR_ARCHIVE_PATH_REJECTED','OCR_RUNTIME_PATH_REJECTED','OCR_RUNTIME_STARTUP_FAILED','OCR_RUNTIME_ALREADY_EXISTS'}
        value.update(state='failed',error=str(error) if str(error) in allowed else 'OCR_SETUP_FAILED',updated=time.time())
    write(state_file,value)
    return True

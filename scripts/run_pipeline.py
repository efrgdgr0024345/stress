"""Bounded cron/service runner. No scheduler or OCR thread inside Passenger."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import signal

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser()
parser.add_argument("--max-seconds",type=int,default=240)
parser.add_argument("--watch",action="store_true",help="Local/supervised development service only")
parser.add_argument("--data-dir",type=Path)
args=parser.parse_args()
settings=ROOT.parent/".config/caesar/caesar-system.json"
if settings.exists():
    if settings.is_symlink() or settings.stat().st_mode&0o077:
        raise SystemExit('Private hosting configuration must be an owner-only regular file.')
    for key,value in json.loads(settings.read_text()).items():
        if key.startswith("CAESAR_"):os.environ.setdefault(key,str(value))
if args.data_dir:os.environ["CAESAR_DATA_DIR"]=str(args.data_dir)
policy=Path(os.environ.get("CAESAR_DATA_DIR",ROOT/".local"))/"pipeline/config.json"
if policy.exists():
    config=json.loads(policy.read_text())
    if config.get("mode")=="bounded_pilot":os.environ["CAESAR_PIPELINE_ALLOW_BOUNDED"]="1"
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
from services.api import main as api,pipeline
from services.api.updates import write
api.initialize()
directory=api.DATA/"pipeline";directory.mkdir(exist_ok=True,mode=0o700)
with (directory/"runner.lock").open("a") as lock:
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit(0)
    start=time.monotonic()
    while args.watch or time.monotonic()-start<args.max_seconds:
        if policy.exists():
            policy_value=json.loads(policy.read_text())
            if policy_value.get("mode")=="bounded_pilot":os.environ["CAESAR_PIPELINE_ALLOW_BOUNDED"]="1"
            else:os.environ.pop("CAESAR_PIPELINE_ALLOW_BOUNDED",None)
        write(directory/"heartbeat.json",{"at":time.time(),"executor":"separate-process","software":pipeline.VERSION})
        from services.api.ocr_setup import run_pending
        if run_pending(api.DATA):continue
        from services.api.digitalocean import advance as advance_provider_demo
        if advance_provider_demo(api):continue
        worked=pipeline.process_one(api)
        if not worked:
            if not args.watch:break
            time.sleep(2)

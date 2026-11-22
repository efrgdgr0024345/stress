"""Account-level worker cron setup; no root or always-on VM required."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser()
parser.add_argument("--bounded-pilot",action="store_true",help="Explicitly allow resource-limited same-account parsing in an access-restricted pilot")
args=parser.parse_args()
settings=ROOT.parent/".config/caesar/caesar-system.json"
if not settings.is_file() or settings.stat().st_mode&0o077:
    raise SystemExit("Owner-only private hosting configuration is required.")
values=json.loads(settings.read_text());data=Path(values["CAESAR_DATA_DIR"])
from services.api.updates import write
write(data/"pipeline/config.json",{"mode":"bounded_pilot" if args.bounded_pilot else "isolated","enabled":True})
runtime=ROOT.parent/"virtualenv/caesar-system/3.12/bin/python"
if not runtime.is_file():runtime=Path(sys.executable)
line=f'*/1 * * * * "{runtime}" "{ROOT}/scripts/run_pipeline.py" --max-seconds 90 >/dev/null 2>&1 # caesar-drawing-pipeline'
if not shutil.which("crontab"):
    print("Add using cPanel Cron Jobs:\n"+line)
else:
    old=subprocess.run(["crontab","-l"],capture_output=True,text=True,timeout=10)
    if old.returncode not in (0,1):raise SystemExit("Could not inspect cron; existing schedules retained.")
    lines=[s for s in old.stdout.splitlines() if not s.endswith("# caesar-drawing-pipeline")]
    subprocess.run(["crontab","-"],input="\n".join(lines+[line])+"\n",text=True,check=True,timeout=10)
    print("Drawing processing scheduled. Jobs continue independently of the browser and Passenger.")
if args.bounded_pilot:print("Restricted pilot adapter selected: resource limits and clean environment, without a separate filesystem sandbox.")

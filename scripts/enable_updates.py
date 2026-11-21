"""Configure the account-private updater and its five-minute cron schedule."""
import json
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from services.api.updates import write, run
settings=json.loads((root.parent/".config/caesar/caesar-system.json").read_text())
directory=Path(settings["CAESAR_DATA_DIR"])/"updates"
parser=argparse.ArgumentParser()
parser.add_argument("--public-dir")
arguments=parser.parse_args()
public=Path(arguments.public_dir).resolve() if arguments.public_dir else root.parent/"easyai.com.au/stress"
if not (public/"loader.php").is_file() or "public_html" in root.parts:
    raise SystemExit("Expected private app and existing EasyAI public folder not found")
write(directory/"config.json",{"app_root":str(root),"public_dir":str(public),"data_dir":settings["CAESAR_DATA_DIR"],"url":"https://easyai.com.au/stress/"})
runtime=root.parent/"virtualenv/caesar-system/3.12/bin/python"
if not runtime.is_file():runtime=Path(sys.executable)
command=f'*/5 * * * * "{runtime}" "{root}/scripts/run_updates.py" >/dev/null 2>&1 # caesar-safe-updater'
if not shutil.which("crontab"):
    print("Add this schedule using cPanel Cron Jobs:\n"+command)
else:
    previous=subprocess.run(["crontab","-l"],capture_output=True,text=True)
    if previous.returncode not in (0,1):raise SystemExit("Could not inspect existing crontab; add the schedule in cPanel manually")
    lines=[line for line in previous.stdout.splitlines() if not line.endswith("# caesar-safe-updater")]
    subprocess.run(["crontab","-"],input="\n".join(lines+[command])+"\n",text=True,check=True)
    run(directory)
    print("Updater enabled. Automatic installation is OFF until enabled by an administrator in the website.")

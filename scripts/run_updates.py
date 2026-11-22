"""Run from cPanel cron, never as a Passenger background thread."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from services.api.updates import run
settings=json.loads((root.parent/".config/caesar/caesar-system.json").read_text())
run(Path(settings["CAESAR_DATA_DIR"])/"updates")
# Existing five-minute installations can advance drawing jobs after upgrading.
# The dedicated one-minute schedule is optional; flock prevents overlap.
import subprocess
subprocess.run([sys.executable,str(root/"scripts/run_pipeline.py"),"--max-seconds","90"],capture_output=True,timeout=360)

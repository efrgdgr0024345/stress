"""Run from cPanel cron, never as a Passenger background thread."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from services.api.updates import run
settings=json.loads((root.parent/".config/caesar/caesar-system.json").read_text())
run(Path(settings["CAESAR_DATA_DIR"])/"updates")

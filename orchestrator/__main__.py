"""Initialize adapter-specific defaults without overwriting operator settings."""
import argparse
import json
from pathlib import Path
from . import default_agents

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["init-config"])
parser.add_argument("directory", type=Path)
args = parser.parse_args()
args.directory.mkdir(parents=True, exist_ok=True)
path = args.directory / "agents.json"
if not path.exists():
    path.write_text(json.dumps({"agents": default_agents()}, indent=2) + "\n", encoding="utf-8")

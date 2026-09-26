"""Optional machine-specific settings, never committed to Git."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def defaults():
    path = BASE / "settings.local.json"
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    source = Path(values.get("source", str(Path.home() / "Downloads"))).expanduser().resolve()
    output = Path(values["output"]).expanduser().resolve() if values.get("output") else None
    return source, output

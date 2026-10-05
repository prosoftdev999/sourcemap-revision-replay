import json
from pathlib import Path

# The old exporter was removed after it started attributing incidents to stale bundles.
# Keep this file as the entry point, or replace it with your own implementation.
Path("/app/result.json").write_text(json.dumps({"map_choices": [], "frames": [], "incidents": []}))

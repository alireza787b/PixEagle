"""Process identity shared by observation contracts and published media."""

import hashlib
import os
from pathlib import Path
import uuid

RUNTIME_ID = str(uuid.uuid4())
_configured_instance = os.environ.get("PIXEAGLE_INSTANCE_ID", "").strip()
INSTANCE_ID = _configured_instance or hashlib.sha256(
    str(Path(__file__).resolve().parents[2]).encode("utf-8")
).hexdigest()
INSTANCE_ID_SOURCE = "configured" if _configured_instance else "local_path"

"""Shared brand data consumed by the native companion and browser product."""
from __future__ import annotations

import json
from pathlib import Path

_DATA = json.loads((Path(__file__).with_name("assets") / "identity.json").read_text(encoding="utf-8"))
NAME: str = _DATA["name"]
COLORS: dict[str, str] = _DATA["colors"]

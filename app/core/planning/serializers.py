from __future__ import annotations

import json
from pathlib import Path

from app.core.planning.models import Plan

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def save_plan(plan: Plan, filename: str = "plan.json") -> Path:
    """
    Serialize a Plan to JSON and save it under data/plan.json by default.
    """
    path = DATA_DIR / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(plan.to_dict(), f, indent=2, default=str)
    return path

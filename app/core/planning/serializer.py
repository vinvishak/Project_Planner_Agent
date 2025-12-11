# app/core/planning/serializers.py

from __future__ import annotations

import json
from pathlib import Path

from core.planning.models import Plan


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def save_plan(plan: Plan, filename: str = "plan.json") -> Path:
    """
    Convert Plan -> dict -> JSON and write to data/plan.json.
    """
    path = DATA_DIR / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(plan.to_dict(), f, indent=2, default=str)
    return path

# app/core/planning/models.py

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional
import datetime as dt


# -----------------------------
# Enums for fixed string values
# -----------------------------

class Status(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TimeHorizon(str, Enum):
    MONTH = "month"
    QUARTER = "quarter"
    HALF_YEAR = "half_year"
    YEAR = "year"


# -----------------------------
# Core data models
# -----------------------------

@dataclass
class Task:
    id: str
    story_id: str
    title: str
    description: str = ""
    estimate: str = "M"  # S, M, L
    status: Status = Status.PLANNED
    labels: List[str] = field(default_factory=list)


@dataclass
class Story:
    id: str
    epic_id: str
    title: str
    description: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)
    priority: Priority = Priority.MEDIUM
    status: Status = Status.PLANNED
    tasks: List[Task] = field(default_factory=list)


@dataclass
class Epic:
    id: str
    title: str
    description: str = ""
    priority: Priority = Priority.HIGH
    status: Status = Status.PLANNED
    stories: List[Story] = field(default_factory=list)


@dataclass
class Sprint:
    id: str
    name: str
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    goal: str = ""
    task_ids: List[str] = field(default_factory=list)


@dataclass
class Plan:
    id: str
    name: str
    vision_text: str
    time_horizon: TimeHorizon
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)
    epics: List[Epic] = field(default_factory=list)
    sprints: List[Sprint] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert this nested structure to a pure dictionary."""
        return asdict(self)

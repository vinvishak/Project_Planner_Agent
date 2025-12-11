# app/core/planning/plan_creation.py

from __future__ import annotations

import datetime as dt
import itertools
import json
import os
import re
from typing import List, Tuple

import openai
import requests
from app.core.planning.models import (
    Plan,
    Epic,
    Story,
    Task,
    Sprint,
    TimeHorizon,
    Priority,
    Status,
)

# Read API key from environment: export OPENAI_API_KEY="sk-..."
openai.api_key = os.environ.get("OPENAI_API_KEY")


def _generate_id(prefix: str, counter: int) -> str:
    """Simple helper to generate ids like EPIC-1, STORY-3, TASK-10, etc."""
    return f"{prefix}-{counter}"


# -------------------------------------------------------------------
# LLM CALL: ask for a text outline (epics + stories + criteria)
# -------------------------------------------------------------------


def _ask_llm_for_outline(vision_text: str) -> str:
    """
    Call the LLM to propose epics and stories in a consistent outline format.
    The LLM returns plain text; we handle structuring in Python.
    """

    if not openai.api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in the environment.")

    system_prompt = (
        "You are a senior product manager. "
        "Given a product vision, you design a clear project structure with epics "
        "and user stories in a consistent outline format."
    )

    user_prompt = f"""
VISION:
\"\"\"{vision_text}\"\"\"

Return an outline in EXACTLY this style:

Epics:
1. <Epic title>
   - <One-line epic description>
   Stories:
   - Story: <Story title>
     Description: <one or two sentences>
     Acceptance criteria:
       - <criterion 1>
       - <criterion 2>
       - <criterion 3>

2. <Next epic title>
   - <One-line epic description>
   Stories:
   - Story: <Story title>
     Description: <one or two sentences>
     Acceptance criteria:
       - <criterion 1>
       - <criterion 2>

Rules:
- Include 3–7 epics.
- Each epic must have at least 1 story.
- Each story must have at least 2 acceptance criteria.
- Use exactly these headings: 'Epics:', 'Stories:', 'Story:', 'Description:', 'Acceptance criteria:'.
- Use '-' bullet points for acceptance criteria.
- Do NOT use JSON.
- Do NOT add explanations before or after the outline.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",  # adjust model if needed
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    outline_text = response.choices[0].message["content"].strip()
    return outline_text


# -------------------------------------------------------------------
# PARSER: outline text -> Epic / Story / Task models
# -------------------------------------------------------------------


def _parse_outline_to_models(outline: str) -> Tuple[List[Epic], List[Task]]:
    """
    Parse the LLM outline text into Epic, Story, Task objects.

    Expected structure (simplified):

    Epics:
    1. Epic title
       - Epic description
       Stories:
       - Story: Story title
         Description: ...
         Acceptance criteria:
           - ...
           - ...
    """

    epics: List[Epic] = []
    all_tasks: List[Task] = []

    epic_counter = itertools.count(1)
    story_counter = itertools.count(1)
    task_counter = itertools.count(1)

    current_epic: Epic | None = None
    current_story: Story | None = None
    collecting_criteria = False
    temp_criteria: List[str] = []

    # We'll capture a simple one-line description for the epic
    last_line_was_epic_title = False

    lines = outline.splitlines()
    for raw_line in lines:
        line = raw_line.rstrip()

        stripped = line.strip()

        # Detect "1. Epic title" style lines
        if re.match(r"^\d+\.\s+", stripped):
            # Close any open story
            if current_story is not None:
                current_story.acceptance_criteria = temp_criteria
                temp_criteria = []
                if current_epic is not None:
                    current_epic.stories.append(current_story)
                current_story = None
                collecting_criteria = False

            # Close previous epic
            if current_epic is not None:
                epics.append(current_epic)

            epic_id = _generate_id("EPIC", next(epic_counter))
            epic_title = stripped.split(".", 1)[1].strip()
            current_epic = Epic(
                id=epic_id,
                title=epic_title,
                description="",
                priority=Priority.HIGH,
                status=Status.PLANNED,
                stories=[],
            )
            last_line_was_epic_title = True
            continue

        # Epic one-line description (we treat the first bullet after the epic title as description)
        if stripped.startswith("- ") and current_epic is not None and last_line_was_epic_title:
            current_epic.description = stripped.lstrip("- ").strip()
            last_line_was_epic_title = False
            continue

        # Detect story header: "- Story: Story title"
        if stripped.startswith("- Story:"):
            # Close previous story
            if current_story is not None:
                current_story.acceptance_criteria = temp_criteria
                temp_criteria = []
                if current_epic is not None:
                    current_epic.stories.append(current_story)
            # New story
            story_id = _generate_id("STORY", next(story_counter))
            story_title = stripped.replace("- Story:", "").strip()
            current_story = Story(
                id=story_id,
                epic_id=current_epic.id if current_epic else "",
                title=story_title,
                description="",
                acceptance_criteria=[],
                priority=Priority.MEDIUM,
                status=Status.PLANNED,
                tasks=[],
            )
            collecting_criteria = False
            continue

        # Story description
        if stripped.startswith("Description:") and current_story is not None:
            current_story.description = stripped.replace("Description:", "").strip()
            continue

        # Start of acceptance criteria block
        if stripped.startswith("Acceptance criteria:") and current_story is not None:
            collecting_criteria = True
            temp_criteria = []
            continue

        # Lines under acceptance criteria
        if stripped.startswith("-") and collecting_criteria and current_story is not None:
            criterion = stripped.lstrip("-").strip()
            if criterion:
                temp_criteria.append(criterion)
            continue

        # Otherwise ignore the line (blank or headings like "Epics:", "Stories:")

    # Close any open story and epic at the end
    if current_story is not None:
        current_story.acceptance_criteria = temp_criteria
        if current_epic is not None:
            current_epic.stories.append(current_story)

    if current_epic is not None:
        epics.append(current_epic)

    # Auto-generate tasks for each story
    for epic in epics:
        for story in epic.stories:
            t1 = Task(
                id=_generate_id("TASK", next(task_counter)),
                story_id=story.id,
                title=f"Setup for: {story.title}",
                description="Create scaffolding, directories, configs, and basic wiring needed for this story.",
                estimate="S",
                status=Status.PLANNED,
                labels=["setup"],
            )
            t2 = Task(
                id=_generate_id("TASK", next(task_counter)),
                story_id=story.id,
                title=f"Implement: {story.title}",
                description="Implement the main logic to satisfy this story.",
                estimate="M",
                status=Status.PLANNED,
                labels=["implementation"],
            )
            t3 = Task(
                id=_generate_id("TASK", next(task_counter)),
                story_id=story.id,
                title=f"Validate: {story.title}",
                description="Test and verify that all acceptance criteria are met.",
                estimate="S",
                status=Status.PLANNED,
                labels=["testing"],
            )
            story.tasks = [t1, t2, t3]
            all_tasks.extend(story.tasks)

    # If something went wrong and we have no epics, create a minimal fallback
    if not epics:
        fallback_epic = Epic(
            id=_generate_id("EPIC", next(epic_counter)),
            title="Initial Project Planning",
            description="Fallback epic generated when outline parsing fails.",
            priority=Priority.MEDIUM,
            status=Status.PLANNED,
            stories=[],
        )
        fallback_story = Story(
            id=_generate_id("STORY", next(story_counter)),
            epic_id=fallback_epic.id,
            title="Create initial project plan",
            description="As a user, I want an initial project plan from my vision.",
            acceptance_criteria=["Plan has at least one epic, story, and task."],
            priority=Priority.MEDIUM,
            status=Status.PLANNED,
            tasks=[],
        )
        fallback_task = Task(
            id=_generate_id("TASK", next(task_counter)),
            story_id=fallback_story.id,
            title="Draft initial project structure",
            description="Manually define epics, stories, and tasks based on the vision.",
            estimate="M",
            status=Status.PLANNED,
            labels=["fallback"],
        )
        fallback_story.tasks = [fallback_task]
        fallback_epic.stories = [fallback_story]
        epics = [fallback_epic]
        all_tasks = [fallback_task]

    return epics, all_tasks


# -------------------------------------------------------------------
# SPRINT ALLOCATION (same idea as before)
# -------------------------------------------------------------------


def _estimate_number_of_sprints(time_horizon: TimeHorizon) -> int:
    if time_horizon == TimeHorizon.MONTH:
        return 2        # ~1 month
    if time_horizon == TimeHorizon.QUARTER:
        return 6        # ~3 months, 6 x 2-week sprints
    if time_horizon == TimeHorizon.HALF_YEAR:
        return 12       # ~6 months
    if time_horizon == TimeHorizon.YEAR:
        return 24       # ~12 months
    return 4            # default fallback


def _allocate_sprints(tasks: List[Task], time_horizon: TimeHorizon) -> List[Sprint]:
    total_sprints = _estimate_number_of_sprints(time_horizon)
    if total_sprints == 0:
        return []

    sprints: List[Sprint] = []
    today = dt.date.today()
    sprint_length_days = 14

    # Create time-boxed sprints
    for i in range(total_sprints):
        start = today + dt.timedelta(days=i * sprint_length_days)
        end = start + dt.timedelta(days=sprint_length_days - 1)
        sprints.append(
            Sprint(
                id=_generate_id("SPRINT", i + 1),
                name=f"Sprint {i + 1}",
                start_date=start,
                end_date=end,
                goal="",
                task_ids=[],
            )
        )

    # Assign tasks into sprints sequentially
    sprint_index = 0
    for task in tasks:
        sprints[sprint_index].task_ids.append(task.id)
        # move to next sprint every 5 tasks (simple heuristic)
        if len(sprints[sprint_index].task_ids) >= 5 and sprint_index < total_sprints - 1:
            sprint_index += 1

    # Simple goals for first couple of sprints
    if sprints:
        sprints[0].goal = "Foundations and scaffolding."
    if len(sprints) > 1:
        sprints[1].goal = "Core planning and meeting capabilities."

    return sprints


# -------------------------------------------------------------------
# PUBLIC ENTRY POINT
# -------------------------------------------------------------------


def create_plan_from_vision(
    plan_name: str,
    vision_text: str,
    time_horizon: TimeHorizon = TimeHorizon.QUARTER,
) -> Plan:
    """
    Main entry point for the Initial Plan Creation module.

    1) Ask LLM for an outline of epics + stories + criteria.
    2) Parse outline into Epic / Story / Task models.
    3) Allocate tasks into sprints.
    4) Return a fully structured Plan object.
    """

    plan_id = "PLAN-1"

    try:
        print("Calling LLM to design plan structure...")
        outline = _ask_llm_for_outline(vision_text)
        epics, all_tasks = _parse_outline_to_models(outline)
        print(f"LLM outline parsed into {len(epics)} epics and {len(all_tasks)} tasks.")
    except Exception as e:
        # In case of any error (no key, API failure, parsing issue), fall back to a minimal plan
        print(f"LLM-based plan generation failed: {e}")
        print("Falling back to a minimal single-epic plan.")
        epics, all_tasks = _parse_outline_to_models("Epics:\n1. Initial Project Planning")

    sprints = _allocate_sprints(all_tasks, time_horizon)

    plan = Plan(
        id=plan_id,
        name=plan_name,
        vision_text=vision_text,
        time_horizon=time_horizon,
        epics=epics,
        sprints=sprints,
    )

    return plan

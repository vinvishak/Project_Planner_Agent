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
import textwrap
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

def _normalize_outline_format(outline: str) -> str:
    """
    Fix indentation and structure so parser can understand the output.
    Ensures:
      EPIC:
        STORY:
        STORY:
    And adds blank lines between EPIC blocks.
    """
    lines = outline.split("\n")
    normalized = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("EPIC:"):
            if normalized:  # add space between EPIC blocks
                normalized.append("")
            normalized.append(stripped)

        elif stripped.startswith("STORY:"):
            # parser expects stories indented under epics
            normalized.append("  " + stripped)

        elif stripped == "":
            continue  # skip excess empty lines

        else:
            # If some extra text appears, just keep it normal
            normalized.append(stripped)

    return "\n".join(normalized)

def _generate_id(prefix: str, counter: int) -> str:
    """Simple helper to generate ids like EPIC-1, STORY-3, TASK-10, etc."""
    return f"{prefix}-{counter}"


# -------------------------------------------------------------------
# LLM CALL: ask for a text outline (epics + stories + criteria)
# -------------------------------------------------------------------


def _ask_llm_for_outline(vision_text: str) -> str:
    """
    Call the local Ollama LLaMA model and return a clean outline string.
    """

    prompt = textwrap.dedent(f"""
    You are a planning assistant. Given a product vision, output an outline of epics and user stories.

    Format your response exactly like this, with no extra sections:

    EPIC: <epic title>
      STORY: <story title>
      STORY: <story title>

    EPIC: <another epic>
      STORY: <story title>

    Vision:
    {vision_text}
    """)

    # Call Ollama /api/generate, non streaming
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2:latest",   # or "llama3:latest" if you prefer
            "prompt": prompt,
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()

    # Ollama returns the text in the 'response' field
    raw_text = data.get("response", "")

    print("\n================ RAW LLaMA OUTLINE ================\n")
    print(raw_text)
    print("\n===================================================\n")

    # Normalize line endings
    normalized = raw_text.replace("\r\n", "\n")

    # Clean common leading junk
    lines = []
    for line in normalized.split("\n"):
        stripped = line.strip()
        # Remove leading bullets like "-", "*", "•"
        stripped = stripped.lstrip("-*•").strip()
        # Remove leading numbers like "1." or "2)"
        stripped = re.sub(r"^[0-9]+[.)]\s*", "", stripped)
        lines.append(stripped)

    cleaned_outline = "\n".join(lines)

    print("\n================ CLEANED OUTLINE ==================\n")
    print(cleaned_outline)
    print("\n===================================================\n")

    outline = _normalize_outline_format(cleaned_outline)

    print("\n================ NORMALIZED OUTLINE FOR PARSER ==================\n")
    print(outline)
    print("\n=================================================================\n")

    return outline


# -------------------------------------------------------------------
# PARSER: outline text -> Epic / Story / Task models
# -------------------------------------------------------------------

def _parse_outline_to_models(outline: str) -> Tuple[List[Epic], List[Task]]:
    """
    Parse the LLM outline text into Epic, Story, Task objects.

    Supports two formats:

    1) Old format (numbered + bullet):
       1. Epic title
          - Epic description
          - Story: Story title
            Description: ...
            Acceptance criteria:
              - ...

    2) New LLaMA format (EPIC/STORY):
       EPIC: Epic title
         STORY: Story title (can be full user story)
         STORY: Another story
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

        # ------------------------------------------------------
        # NEW FORMAT: "EPIC: <title>"
        # ------------------------------------------------------
        if stripped.startswith("EPIC:"):
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
            epic_title = stripped[len("EPIC:"):].strip()
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

        # ------------------------------------------------------
        # NEW FORMAT: "STORY: <full user story>"
        # ------------------------------------------------------
        if stripped.startswith("STORY:"):
            # Close previous story
            if current_story is not None:
                current_story.acceptance_criteria = temp_criteria
                temp_criteria = []
                if current_epic is not None:
                    current_epic.stories.append(current_story)

            # If there is no current epic yet, create a generic one
            if current_epic is None:
                epic_id = _generate_id("EPIC", next(epic_counter))
                current_epic = Epic(
                    id=epic_id,
                    title="General",
                    description="Auto-created epic for orphan stories.",
                    priority=Priority.MEDIUM,
                    status=Status.PLANNED,
                    stories=[],
                )

            story_id = _generate_id("STORY", next(story_counter))
            story_title = stripped[len("STORY:"):].strip()
            current_story = Story(
                id=story_id,
                epic_id=current_epic.id,
                title=story_title,
                description="",
                acceptance_criteria=[],
                priority=Priority.MEDIUM,
                status=Status.PLANNED,
                tasks=[],
            )
            collecting_criteria = False
            last_line_was_epic_title = False
            continue

        # ------------------------------------------------------
        # OLD FORMAT: "1. Epic title"
        # ------------------------------------------------------
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

        # Epic one-line description (old format)
        if stripped.startswith("- ") and current_epic is not None and last_line_was_epic_title:
            current_epic.description = stripped.lstrip("- ").strip()
            last_line_was_epic_title = False
            continue

        # OLD FORMAT: "- Story: Story title"
        if stripped.startswith("- Story:"):
            # Close previous story
            if current_story is not None:
                current_story.acceptance_criteria = temp_criteria
                temp_criteria = []
                if current_epic is not None:
                    current_epic.stories.append(current_story)

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

    # ------------------------------------------------------
    # Close any open story and epic at the end
    # ------------------------------------------------------
    if current_story is not None:
        current_story.acceptance_criteria = temp_criteria
        if current_epic is not None:
            current_epic.stories.append(current_story)

    if current_epic is not None:
        epics.append(current_epic)

    # ------------------------------------------------------
    # Auto-generate tasks for each story
    # ------------------------------------------------------
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

    # ------------------------------------------------------
    # Fallback if absolutely nothing parsed
    # ------------------------------------------------------
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


def _allocate_sprints(
    epics: List[Epic],
    tasks: List[Task],
    time_horizon: TimeHorizon,
    vision_text: str,
) -> List[Sprint]:
    total_sprints = _estimate_number_of_sprints(time_horizon)
    if total_sprints == 0:
        return []

    sprints: List[Sprint] = []
    today = dt.date.today()
    sprint_length_days = 14

    # Create time boxed sprints
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

    if not tasks:
        # No tasks, just set very high level goals
        for i, sprint in enumerate(sprints):
            if i == 0:
                sprint.goal = "Initial setup and discovery."
            elif i == 1:
                sprint.goal = "Core implementation."
            else:
                sprint.goal = "Ongoing improvements."
        return sprints

    # Simple sequential assignment of tasks into sprints
    sprint_index = 0
    for task in tasks:
        sprints[sprint_index].task_ids.append(task.id)
        # move to next sprint every 5 tasks (simple heuristic)
        if len(sprints[sprint_index].task_ids) >= 5 and sprint_index < total_sprints - 1:
            sprint_index += 1

    # Build lookup maps to understand which epic each task belongs to
    story_by_id = {}
    epic_by_id = {}

    for epic in epics:
        epic_by_id[epic.id] = epic
        for story in epic.stories:
            story_by_id[story.id] = story

    # Helper to get a short project label from the vision text
    first_line = vision_text.strip().splitlines()[0] if vision_text.strip() else "this project"
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."

    # Set a specific goal for each sprint based on its tasks and epics
    for i, sprint in enumerate(sprints):
        epic_titles_in_sprint = []

        for task in tasks:
            if task.id in sprint.task_ids:
                story = story_by_id.get(task.story_id)
                if story:
                    epic = epic_by_id.get(story.epic_id)
                    if epic:
                        epic_titles_in_sprint.append(epic.title)

        # Unique epic titles, preserve order
        seen = set()
        unique_epic_titles = []
        for title in epic_titles_in_sprint:
            if title not in seen:
                unique_epic_titles.append(title)
                seen.add(title)

        if unique_epic_titles:
            # Only show at most three epic names
            if len(unique_epic_titles) > 3:
                epic_list_str = ", ".join(unique_epic_titles[:3]) + ", and others"
            else:
                epic_list_str = ", ".join(unique_epic_titles)
        else:
            epic_list_str = "key epics"

        if i == 0:
            sprint.goal = f"Foundations for '{first_line}'. Focus on {epic_list_str}."
        elif i == 1:
            sprint.goal = f"Core implementation for {epic_list_str}."
        elif i == 2:
            sprint.goal = f"Refinement and validation for {epic_list_str}."
        else:
            sprint.goal = f"Ongoing improvements across {epic_list_str}."

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
        print("Outline text returned from LLaMA:\n", outline)
        epics, all_tasks = _parse_outline_to_models(outline)
        print(f"LLM outline parsed into {len(epics)} epics and {len(all_tasks)} tasks.")
    except Exception as e:
        # In case of any error (no key, API failure, parsing issue), fall back to a minimal plan
        print(f"LLM-based plan generation failed: {e}")
        print("Falling back to a minimal single-epic plan.")
        epics, all_tasks = _parse_outline_to_models("Epics:\n1. Initial Project Planning")

    sprints = _allocate_sprints(epics, all_tasks, time_horizon, vision_text)

    plan = Plan(
        id=plan_id,
        name=plan_name,
        vision_text=vision_text,
        time_horizon=time_horizon,
        epics=epics,
        sprints=sprints,
    )

    return plan

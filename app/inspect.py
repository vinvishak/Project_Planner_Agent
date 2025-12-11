# app/inspect.py

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    data_path = Path("data/plan.json")

    if not data_path.exists():
        print("❌ No plan found. Run `python -m app.main` first to create one.")
        return

    with data_path.open("r", encoding="utf-8") as f:
        plan = json.load(f)

    print("\n=== PLAN INFO ===")
    print(f"Plan ID:   {plan.get('id')}")
    print(f"Name:      {plan.get('name')}")
    print(f"Horizon:   {plan.get('time_horizon')}")
    print()

    epics = plan.get("epics", [])
    print(f"Total epics:  {len(epics)}")

    for e_index, epic in enumerate(epics, start=1):
        print(f"\n--- Epic {e_index}: {epic.get('title')} ---")
        print(f"ID:          {epic.get('id')}")
        print(f"Description: {epic.get('description')}")
        print(f"Priority:    {epic.get('priority')}")
        print()

        stories = epic.get("stories", [])
        print(f"  Stories in this epic: {len(stories)}")

        for s_index, story in enumerate(stories, start=1):
            print(f"  [{s_index}] Story: {story.get('title')}")
            print(f"      ID:          {story.get('id')}")
            print(f"      Description: {story.get('description')}")
            print(f"      Priority:    {story.get('priority')}")
            ac = story.get("acceptance_criteria", [])
            if ac:
                print("      Acceptance criteria:")
                for c in ac:
                    print(f"        - {c}")

            tasks = story.get("tasks", [])
            print(f"      Tasks ({len(tasks)}):")
            for t_index, task in enumerate(tasks, start=1):
                print(f"        ({t_index}) {task.get('title')}")
                print(f"             ID:       {task.get('id')}")
                print(f"             Estimate: {task.get('estimate')}")
                print(f"             Status:   {task.get('status')}")
                labels = task.get("labels") or []
                if labels:
                    print(f"             Labels:   {', '.join(labels)}")

    # Sprints summary
    sprints = plan.get("sprints", [])
    print("\n=== SPRINTS ===")
    print(f"Total sprints: {len(sprints)}")
    for sp_index, sprint in enumerate(sprints, start=1):
        print(
            f"  Sprint {sp_index}: {sprint.get('name')} "
            f"({sprint.get('start_date')} → {sprint.get('end_date')})"
        )
        print(f"      Goal:      {sprint.get('goal')}")
        print(f"      Task IDs:  {', '.join(sprint.get('task_ids', []))}")


if __name__ == "__main__":
    main()

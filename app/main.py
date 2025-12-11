# app/main.py

from app.core.planning.plan_creation import create_plan_from_vision
from app.core.planning.models import TimeHorizon
from app.core.planning.serializers import save_plan


def main():
    print("=== Project Planner Agent ===")

    plan_name = input("Plan name (press Enter for default): ").strip()
    if not plan_name:
        plan_name = "My Project Plan"

    print("\nEnter your project vision (finish by pressing Enter on an empty line):")
    lines = []
    while True:
        line = input()
        if not line.strip():  # empty line ends input
            break
        lines.append(line)

    vision_text = "\n".join(lines).strip()

    if not vision_text:
        print("⚠️  No vision provided. Exiting.")
        return

    print("\nCreating plan using LLM...")
    plan = create_plan_from_vision(
        plan_name=plan_name,
        vision_text=vision_text,
        time_horizon=TimeHorizon.QUARTER,
    )

    path = save_plan(plan)
    print(f"\nPlan successfully saved to: {path}")
    print("\nYou can view the full plan by running:")
    print("   python -m app.inspect")


if __name__ == "__main__":
    main()

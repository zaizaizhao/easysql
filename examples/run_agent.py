"""
Example script to run EasySQL Agent.

Demonstrates HITL (Plan mode) and Fast mode.
"""

import uuid
from typing import Any

from easysql.config import load_settings
from easysql.llm import build_graph


def run_agent_demo():
    """Run the EasySQL Agent in interactive mode."""
    # Load settings (ensure .env is set)
    settings = load_settings()

    print(f"--- EasySQL Agent Demo (Mode: {settings.llm.query_mode}) ---")
    print(f"    Provider: {settings.llm.get_provider()}")
    print(f"    Model: {settings.llm.get_model()}")
    if settings.llm.model_planning:
        print(f"    Planning Model: {settings.llm.model_planning}")

    # Show available databases
    if settings.databases:
        db_names = list(settings.databases.keys())
        print(f"    Databases: {', '.join(db_names)}")
        default_db = db_names[0] if db_names else None
    else:
        print("    Warning: No databases configured!")
        default_db = None

    # Build Graph
    graph = build_graph()

    # Unique thread ID for state persistence
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print(
        "\nType your question to generate SQL. Commands: 'q' to quit, 'db:<name>' to switch database\n"
    )

    current_db = default_db

    # Interactive loop
    while True:
        try:
            user_input = input(f"[{current_db or 'no-db'}] > ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["q", "quit", "exit"]:
                print("Goodbye!")
                break

            # Switch database command
            if user_input.lower().startswith("db:"):
                new_db = user_input[3:].strip()
                if new_db in (settings.databases or {}):
                    current_db = new_db
                    print(f"Switched to database: {current_db}")
                else:
                    print(
                        f"Database '{new_db}' not found. Available: {list(settings.databases.keys())}"
                    )
                continue

            input_state = {
                "raw_query": user_input,
                "clarified_query": None,
                "clarification_questions": None,
                "messages": [],
                "schema_hint": None,
                "retrieval_result": None,
                "context_output": None,
                "generated_sql": None,
                "validation_result": None,
                "validation_passed": False,
                "retry_count": 0,
                "error": None,
                "db_name": current_db,
            }

            print("\n--- Processing ---")

            # Invoke graph
            result = graph.invoke(input_state, config)

            # Check for interrupt (HITL - clarification needed)
            snapshot = graph.get_state(config)

            while snapshot.next:
                print(f"--- Paused at: {snapshot.next} ---")

                # Handle clarification interrupt
                if "clarify" in snapshot.next:
                    # Get interrupt payload if available
                    interrupt_info = _get_interrupt_info(snapshot)
                    if interrupt_info:
                        print(f"\n{interrupt_info.get('question', 'Clarification needed:')}")
                    else:
                        print("\nAgent needs clarification.")

                    answer = input("Your answer > ").strip()

                    if answer.lower() in ["q", "quit"]:
                        break

                    # Resume with user's answer
                    from langgraph.types import Command

                    result = graph.invoke(Command(resume=answer), config)

                    # Check if there are more interrupts
                    snapshot = graph.get_state(config)
                else:
                    # Unknown pause state
                    print(f"Unexpected pause at {snapshot.next}")
                    break

            # Output final result
            _print_result(result)

            # Start new thread for next question (clean state)
            thread_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": thread_id}}

        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye!")
            break
        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"\nError: {e}")
            print("Try again or type 'q' to quit.\n")


def _get_interrupt_info(snapshot: Any) -> dict | None:
    """Extract interrupt payload from snapshot if available."""
    try:
        if hasattr(snapshot, "tasks") and snapshot.tasks:
            for task in snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    for interrupt in task.interrupts:
                        if hasattr(interrupt, "value"):
                            return interrupt.value
    except Exception:
        pass
    return None


def _print_result(result: dict) -> None:
    """Print the agent result in a formatted way."""
    if result.get("generated_sql"):
        print(f"\n{'=' * 50}")
        print("Generated SQL:")
        print(f"{'=' * 50}")
        print(result["generated_sql"])
        print(f"{'=' * 50}")

        if result.get("validation_passed"):
            print("✓ Validation Passed")
        else:
            error = result.get("error") or result.get("validation_result", {}).get("error")
            print(f"✗ Validation Failed: {error or 'Unknown error'}")
    else:
        print("\n⚠ No SQL generated.")
        if result.get("error"):
            print(f"   Error: {result['error']}")


if __name__ == "__main__":
    run_agent_demo()

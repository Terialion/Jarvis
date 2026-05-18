"""End-to-end verification: simulate real conversation flow and print the exact
messages sent to the LLM.

This mirrors what AgentLoop.run_turn / run_turn_stream does:
  1. Create session + turn
  2. Persist user message to JSONL (simulating loop.py line 611)
  3. Build context + prompt (simulating context_builder.build_messages)
  4. Print the final messages list
"""
import sys
import json
from pathlib import Path

from jarvis.agent.context import ContextBuilder
from jarvis.agent.prompt_builder import PromptBuilder
from jarvis.agent.store import ThreadStore
from jarvis.agent.types import ChatInput
from jarvis.skills.registry import SkillRegistry


def sep(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_messages(messages: list[dict], current_text: str) -> None:
    count = 0
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = str(msg.get("content", ""))
        if role == "system":
            preview = content[:100] + "..." if len(content) > 100 else content
        else:
            preview = content
        dup = " <-- DUPLICATE!" if (role == "user" and content == current_text and count > 0) else ""
        if role == "user" and content == current_text:
            count += 1
        print(f"  [{i}] {role:10} | {preview[:150]}{dup}")
    print(f"\n  => '{current_text}' appears {count} time(s) as user-role message")


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        store = ThreadStore(root=tmp_path / "threads")

        sid = "demo_session"

        # --- Simulate 2 prior turns ---
        sep("Simulating 2 prior conversation turns")

        t1 = store.create_turn(sid)
        store.append_message(sid, t1.turn_id, "user", "list project tree")
        store.append_message(sid, t1.turn_id, "assistant", "src/jarvis/ with cli.py, agent/, tools/...")
        print(f"  Turn 1 ({t1.turn_id}): user -> assistant")

        t2 = store.create_turn(sid)
        store.append_message(sid, t2.turn_id, "user", "how many lines in cli.py?")
        store.append_message(sid, t2.turn_id, "assistant", "About 4100 lines.")
        print(f"  Turn 2 ({t2.turn_id}): user -> assistant")

        # --- Turn 3: current request (loop.py line 611) ---
        current_text = "where is main() in cli.py?"
        t3 = store.create_turn(sid)
        store.append_message(sid, t3.turn_id, "user", current_text)
        print(f"  Turn 3 ({t3.turn_id}): CURRENT (persisted to JSONL before build)")

        # --- Build context (loop.py line 621) ---
        sep("Building context (context_builder.build_messages)")
        builder = ContextBuilder(session_store=store, skill_registry=SkillRegistry())
        prompt_builder = PromptBuilder()

        turn_context, messages = builder.build_messages(
            session_id=sid,
            turn_id=t3.turn_id,
            chat_input=ChatInput(text=current_text, cwd=str(tmp_path), project_id="demo"),
            prompt_builder=prompt_builder,
        )
        print(f"  Total messages assembled: {len(messages)}")

        # --- Print final messages ---
        sep("Messages sent to LLM")
        print_messages(messages, current_text)

        # --- Verify ---
        sep("Verification")
        errors = []

        user_msgs = [m for m in messages if m.get("role") == "user" and m.get("content") == current_text]
        if len(user_msgs) == 1:
            print("  [OK] Current input appears exactly once")
        else:
            errors.append(f"Current input appears {len(user_msgs)} times (expected 1)")

        if any(m.get("content") == "list project tree" for m in messages):
            print("  [OK] Prior turn 1 user message present")
        else:
            errors.append("Prior turn 1 user message missing")

        if any(m.get("content") == "About 4100 lines." for m in messages):
            print("  [OK] Prior turn 2 assistant message present")
        else:
            errors.append("Prior turn 2 assistant message missing")

        total_users = sum(1 for m in messages if m.get("role") == "user")
        if total_users == 3:
            print(f"  [OK] Total user messages: {total_users} (2 prior + 1 current)")
        else:
            errors.append(f"Expected 3 user messages, got {total_users}")

        if errors:
            print(f"\n  {len(errors)} ERROR(S):")
            for e in errors:
                print(f"    - {e}")
            sys.exit(1)
        else:
            print("\n  All checks passed. No duplicate user input bug.")

        # --- Show JSONL for comparison ---
        sep("JSONL contents (all persisted messages)")
        # ThreadStore creates sessions dir under the configured root
        from pathlib import Path as P
        candidates = list(tmp_path.rglob("*.jsonl"))
        if candidates:
            for line in candidates[0].read_text(encoding="utf-8").strip().split("\n"):
                obj = json.loads(line)
                print(f"  turn={obj.get('turn_id','?')[:24]:25} role={obj.get('role','?'):12} content={str(obj.get('content',''))[:60]}")
        else:
            print("  (no JSONL found — session files stored elsewhere)")


if __name__ == "__main__":
    main()

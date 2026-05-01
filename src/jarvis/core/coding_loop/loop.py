from __future__ import annotations

import difflib
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .evidence import append_coding_loop_trace
from .judge import judge_coding_success
from .replan import replan_from_rethink
from .rethink import rethink_after_failure
from .schema import CodingLoopState, Observation
from .scoped_tests import run_scoped_fixture_tests
from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.provider import LLMProvider


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_patch_diff(before: str, after: str, relpath: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
            lineterm="",
        )
    )


def _apply_greeting_patch(target_file: Path, *, first_attempt_wrong: bool) -> dict[str, Any]:
    before = target_file.read_text(encoding="utf-8")
    if first_attempt_wrong:
        candidate = before.replace('return f"Hello, {name}"', 'return f"Hi, {name}"')
    else:
        candidate = before.replace('return f"Hello, {name}"', 'return f"Hello, {name}!"')
    if candidate == before:
        return {"ok": False, "changed": False, "summary": "Expected greeting line not found."}
    target_file.write_text(candidate, encoding="utf-8")
    return {
        "ok": True,
        "changed": True,
        "summary": "Greeting function patched.",
        "diff": _build_patch_diff(before, candidate, "examples/coding_fixture/greeting.py"),
    }


def run_coding_loop_for_fixture(
    *,
    workspace_root: Path,
    task_id: str,
    user_goal: str,
    max_rounds: int = 3,
    auto_approve: bool = True,
    force_first_failure: bool = False,
    trace_path: Path | None = None,
    instructions: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
) -> dict[str, Any]:
    target_file = workspace_root / "examples" / "coding_fixture" / "greeting.py"
    if not target_file.exists():
        raise FileNotFoundError(f"Missing fixture file: {target_file}")

    state = CodingLoopState(
        task_id=task_id,
        workspace_root=str(workspace_root),
        user_goal=user_goal,
        current_plan=[
            "Inspect greeting fixture and test expectation.",
            "Prepare minimal patch in greeting function.",
            "Run scoped tests for fixture only.",
        ],
        max_rounds=max_rounds,
        status="planning",
    )
    trace_file = trace_path or (workspace_root / "temp" / "coding_loop" / "smoke_runs.jsonl")
    initial_hash = _sha256(target_file)
    append_coding_loop_trace(trace_file, {"task_id": task_id, "phase": "start", "initial_file_hash": initial_hash})

    while state.round < state.max_rounds:
        state.round += 1
        state.status = "approval_required"
        approval = {"round": state.round, "kind": "write_and_shell", "status": "pending"}
        state.approvals.append(approval)
        before_hash = _sha256(target_file)
        pre_shell_executed = len(state.test_results)

        if not auto_approve:
            approval["status"] = "denied"
            state.observations.append(
                Observation(
                    round=state.round,
                    type="approval_result",
                    ok=False,
                    summary="Approval denied by policy.",
                    details={"round": state.round},
                )
            )
            decision = judge_coding_success(state, instructions=instructions, llm_provider=llm_provider)
            state.stop_reason = decision.stop_reason
            state.status = "blocked"
            append_coding_loop_trace(trace_file, {"task_id": task_id, "round": state.round, "decision": asdict(decision)})
            break

        approval["status"] = "approved"
        state.observations.append(
            Observation(round=state.round, type="approval_result", ok=True, summary="Approval granted.", details={"round": state.round})
        )

        patch_result = _apply_greeting_patch(target_file, first_attempt_wrong=force_first_failure and state.round == 1)
        state.actions.append({"round": state.round, "action": "apply_patch", "ok": patch_result["ok"]})
        state.observations.append(
            Observation(
                round=state.round,
                type="patch_result",
                ok=bool(patch_result["ok"]),
                summary=str(patch_result.get("summary", "")),
                details={"changed": patch_result.get("changed", False)},
            )
        )
        if patch_result.get("diff"):
            state.diffs.append({"round": state.round, "diff": patch_result["diff"]})

        test_result = run_scoped_fixture_tests(workspace_root)
        state.test_results.append(test_result)
        state.actions.append({"round": state.round, "action": "run_scoped_test", "ok": bool(test_result.get("passed"))})
        state.observations.append(
            Observation(
                round=state.round,
                type="test_result",
                ok=bool(test_result.get("passed")),
                summary="Scoped tests passed." if test_result.get("passed") else "Scoped tests failed.",
                details={"command": test_result.get("command"), "exit_code": test_result.get("exit_code")},
            )
        )

        decision = judge_coding_success(state, instructions=instructions, llm_provider=llm_provider)
        append_coding_loop_trace(
            trace_file,
            {
                "task_id": task_id,
                "round": state.round,
                "plan": list(state.current_plan),
                "approval": dict(approval),
                "patch_result": patch_result,
                "test_result": test_result,
                "decision": asdict(decision),
                "file_hash_before": before_hash,
                "file_hash_after": _sha256(target_file),
                "pre_shell_count": pre_shell_executed,
                "post_shell_count": len(state.test_results),
            },
        )

        if decision.decision == "success":
            state.status = "success"
            state.stop_reason = decision.stop_reason
            break
        if decision.decision == "replan":
            rethink_record = rethink_after_failure(state, state.observations[-1], instructions=instructions, llm_provider=llm_provider)
            state.rethink_records.append(rethink_record)
            state.current_plan = replan_from_rethink(state, rethink_record, instructions=instructions, llm_provider=llm_provider)
            append_coding_loop_trace(
                trace_file,
                {"task_id": task_id, "round": state.round, "rethink_record": asdict(rethink_record), "replan": list(state.current_plan)},
            )
            continue
        if decision.decision in {"blocked", "max_rounds"}:
            state.status = "blocked" if decision.decision == "blocked" else "max_rounds"
            state.stop_reason = decision.stop_reason
            break

    if not state.stop_reason:
        final_decision = judge_coding_success(state, instructions=instructions, llm_provider=llm_provider)
        state.stop_reason = final_decision.stop_reason
        if final_decision.decision == "max_rounds":
            state.status = "max_rounds"
        elif final_decision.decision == "success":
            state.status = "success"
        else:
            state.status = "failed"

    return {
        "task_id": state.task_id,
        "rounds": state.round,
        "status": state.status,
        "stop_reason": state.stop_reason,
        "observations": [asdict(item) for item in state.observations],
        "approvals": list(state.approvals),
        "diffs": list(state.diffs),
        "test_results": list(state.test_results),
        "rethink_records": [asdict(item) for item in state.rethink_records],
        "trace_path": str(trace_file),
        "final_file_hash": _sha256(target_file),
        "initial_file_hash": initial_hash,
        "instruction_sources": [source.__dict__ for source in instructions.sources] if instructions else [],
    }

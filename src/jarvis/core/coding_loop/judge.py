from __future__ import annotations

from dataclasses import asdict

from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.prompt_builder import build_success_judge_prompt
from src.jarvis.core.llm.provider import LLMProvider, safe_complete

from .schema import CodingLoopState, LoopDecision


def judge_coding_success(
    state: CodingLoopState,
    *,
    instructions: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
) -> LoopDecision:
    for approval in reversed(state.approvals):
        if approval.get("status") == "denied":
            return _with_llm_explanation(
                LoopDecision(
                    decision="blocked",
                    success=False,
                    confidence=1.0,
                    stop_reason="approval_denied",
                    why="Approval was denied by policy or operator.",
                    risk_level="medium",
                ),
                state,
                instructions,
                llm_provider,
            )

    if any(obs.type == "safety_violation" for obs in state.observations):
        return _with_llm_explanation(LoopDecision(
            decision="blocked",
            success=False,
            confidence=1.0,
            stop_reason="unsafe",
            why="Safety policy violation detected.",
            risk_level="high",
        ), state, instructions, llm_provider)

    if not state.observations:
        if state.round >= state.max_rounds:
            return _with_llm_explanation(LoopDecision(
                decision="max_rounds",
                success=False,
                confidence=1.0,
                stop_reason="max_rounds",
                why="Maximum rounds reached without success.",
            ), state, instructions, llm_provider)
        return _with_llm_explanation(LoopDecision(
            decision="inspect_more",
            success=False,
            confidence=0.4,
            stop_reason="missing_context",
            why="No observations recorded yet.",
            required_actions=["inspect_more"],
        ), state, instructions, llm_provider)

    patch_ok = any(obs.type == "patch_result" and obs.ok for obs in state.observations)
    tests_passed = bool(state.test_results) and bool(state.test_results[-1].get("passed"))
    pending_approval = any(item.get("status") == "pending" for item in state.approvals)
    if patch_ok and tests_passed and not pending_approval:
        return _with_llm_explanation(LoopDecision(
            decision="success",
            success=True,
            confidence=1.0,
            stop_reason="done",
            why="Patch applied and scoped tests passed.",
        ), state, instructions, llm_provider)

    if state.round >= state.max_rounds:
        return _with_llm_explanation(LoopDecision(
            decision="max_rounds",
            success=False,
            confidence=1.0,
            stop_reason="max_rounds",
            why="Maximum rounds reached without success.",
        ), state, instructions, llm_provider)

    last_obs = state.observations[-1]
    if last_obs.type == "patch_result" and not last_obs.ok:
        return _with_llm_explanation(LoopDecision(
            decision="replan",
            success=False,
            confidence=0.85,
            stop_reason="patch_failed",
            why=last_obs.summary,
            required_actions=["inspect_more", "replan"],
            requires_approval=False,
            risk_level="medium",
        ), state, instructions, llm_provider)

    if state.test_results:
        last_test = state.test_results[-1]
        if not bool(last_test.get("passed")):
            return _with_llm_explanation(LoopDecision(
                decision="replan",
                success=False,
                confidence=0.9,
                stop_reason="test_failed",
                why="Scoped test failed and needs rethink/replan.",
                required_actions=["rethink", "patch", "run_scoped_test"],
                requires_approval=True,
                risk_level="medium",
            ), state, instructions, llm_provider)

    return _with_llm_explanation(LoopDecision(
        decision="approval_required",
        success=False,
        confidence=0.8,
        stop_reason="approval_required",
        why="Write/shell actions still require approval.",
        required_actions=["approval"],
        requires_approval=True,
    ), state, instructions, llm_provider)


def _with_llm_explanation(
    decision: LoopDecision,
    state: CodingLoopState,
    instructions: InstructionBundle | None,
    llm_provider: LLMProvider | None,
) -> LoopDecision:
    prompt = build_success_judge_prompt(instructions=instructions, state=_state_payload(state))
    explanation = safe_complete(llm_provider, prompt, system="Explain the deterministic coding-loop decision. Do not change it.")
    if explanation:
        decision.why = f"{decision.why} LLM note: {explanation[:240]}"
    return decision


def _state_payload(state: CodingLoopState) -> dict:
    return {
        "task_id": state.task_id,
        "round": state.round,
        "max_rounds": state.max_rounds,
        "observations": [asdict(item) for item in state.observations],
        "approvals": list(state.approvals),
        "test_results": list(state.test_results),
        "status": state.status,
        "stop_reason": state.stop_reason,
    }

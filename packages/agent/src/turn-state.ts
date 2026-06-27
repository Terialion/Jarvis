export type AgentTurnState =
  | "completed"
  | "waiting_for_user"
  | "waiting_for_plan_review"
  | "blocked"
  | "timed_out"
  | "interrupted"
  | "failed";

export function mapStopReasonToTurnState(stopReason: string): AgentTurnState {
  if (stopReason === "waiting_for_plan_edits") return "waiting_for_plan_review";
  if (["question_cancelled", "plan_cancelled", "approval_required", "consecutive_rejections"].includes(stopReason)) {
    return "waiting_for_user";
  }
  if (["timeout", "finalize_timeout"].includes(stopReason)) return "timed_out";
  if (["interrupted", "superseded_by_new_prompt"].includes(stopReason)) return "interrupted";
  if (["llm_error", "consecutive_failures"].includes(stopReason)) return "failed";
  if (["retry_with_tool_instruction", "no_progress", "max_steps"].includes(stopReason)) return "blocked";
  return "completed";
}

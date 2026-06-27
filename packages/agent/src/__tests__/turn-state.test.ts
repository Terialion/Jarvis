import { describe, expect, it } from "vitest";
import { mapStopReasonToTurnState } from "../turn-state.js";

describe("mapStopReasonToTurnState", () => {
  it("maps finalize and timeout style stops to timed_out", () => {
    expect(mapStopReasonToTurnState("finalize_timeout")).toBe("timed_out");
    expect(mapStopReasonToTurnState("timeout")).toBe("timed_out");
  });

  it("maps user-facing pauses to waiting states", () => {
    expect(mapStopReasonToTurnState("waiting_for_plan_edits")).toBe("waiting_for_plan_review");
    expect(mapStopReasonToTurnState("approval_required")).toBe("waiting_for_user");
  });

  it("maps retry and no-progress stops to blocked", () => {
    expect(mapStopReasonToTurnState("retry_with_tool_instruction")).toBe("blocked");
    expect(mapStopReasonToTurnState("no_progress")).toBe("blocked");
  });

  it("defaults unknown completed-style reasons to completed", () => {
    expect(mapStopReasonToTurnState("completed")).toBe("completed");
    expect(mapStopReasonToTurnState("finalized_after_stagnation")).toBe("completed");
  });
});

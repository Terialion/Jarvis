import React from "react";
import { describe, expect, it } from "vitest";
import { buildCodexTimelineState } from "../presentation/codex-timeline-state.js";
import { buildCodexTranscriptItems } from "../presentation/CodexTimeline.js";

describe("buildCodexTranscriptItems", () => {
  it("expands a turn block into stable header and item keys", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "reason_1", type: "reasoning", text: "Inspecting files." },
        },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "tool_1", type: "tool_call", tool_name: "read", status: "completed", arguments: { path: "README.md" }, result: "Loaded" },
        },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "msg_1", type: "agent_message", text: "Done." },
        },
        { type: "turn.completed", turn_id: "turn_1", stop_reason: "stop" },
      ],
      liveStatus: { isLoading: false },
      messages: [{ id: "user_1", role: "user", text: "hello" }],
    });

    const items = buildCodexTranscriptItems({
      state,
      detailsExpanded: false,
    });

    expect(items.map((item) => item.id)).toEqual([
      "user:user_1",
      "turn:turn_1:header",
      "turn:turn_1:item:reason_1",
      "turn:turn_1:item:tool_1",
      "turn:turn_1:item:msg_1",
    ]);
  });

  it("keeps item identities stable while details expansion changes rendering only", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "msg_1", type: "agent_message", text: "Final answer." },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [{ id: "user_1", role: "user", text: "hello" }],
    });

    const collapsed = buildCodexTranscriptItems({ state, detailsExpanded: false });
    const expanded = buildCodexTranscriptItems({ state, detailsExpanded: true });

    expect(expanded.map((item) => item.id)).toEqual(collapsed.map((item) => item.id));
  });
});

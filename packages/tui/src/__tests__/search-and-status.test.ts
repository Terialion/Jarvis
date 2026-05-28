import { describe, expect, it } from "vitest";
import { buildStatusSegments, getProjectLabel } from "../status-segments.js";
import {
  buildSearchExcerpt,
  extractProgressLines,
  summarizeToolUse,
  type Message,
} from "../vendor/ui/MessageList.js";
import { computeMatches } from "../vendor/ui/SearchOverlay.js";
import { buildCodexTimelineState } from "../presentation/codex-timeline-state.js";

describe("computeMatches", () => {
  it("finds case-insensitive matches across messages", () => {
    const matches = computeMatches(["Alpha beta", "gamma ALPHA", "no hit here"], "alpha");

    expect(matches).toEqual([
      { index: 0, offset: 0, length: 5 },
      { index: 1, offset: 6, length: 5 },
    ]);
  });

  it("returns an empty list for an empty query", () => {
    expect(computeMatches(["alpha"], "")).toEqual([]);
  });
});

describe("buildStatusSegments", () => {
  it("builds codex-style status metadata with key runtime signals", () => {
    const segments = buildStatusSegments({
      cwd: "D:/agent/Jarvis",
      model: "gpt-5-codex",
      gitBranch: "codex/tui-pass-1",
      isLoading: true,
      hasQuestion: false,
      totalTokens: 12345,
      contextPercentRemaining: 72,
      taskCounts: { pending: 2, in_progress: 1, completed: 3 },
      elapsedMs: 65_000,
      sessionId: "session_12345678",
    });

    expect(segments.map((segment) => segment.content)).toEqual([
      "project Jarvis",
      "branch codex/tui-pass-1",
      "model gpt-5-codex",
      "state Working",
      "12,345 tok | 72% left",
      "tasks ~1 o2 x3",
      "1m 05s",
      "session 12345678",
    ]);
  });

  it("prefers Question over Working when user input is requested", () => {
    const segments = buildStatusSegments({
      cwd: "D:/agent/Jarvis",
      model: "deepseek-chat",
      isLoading: true,
      hasQuestion: true,
      taskCounts: { pending: 0, in_progress: 0, completed: 0 },
      elapsedMs: 0,
    });

    expect(segments[1]?.content).toBe("model deepseek-chat");
    expect(segments[2]?.content).toBe("state Question");
  });
});

describe("getProjectLabel", () => {
  it("uses the cwd basename", () => {
    expect(getProjectLabel("D:/agent/Jarvis")).toBe("Jarvis");
  });
});

describe("summarizeToolUse", () => {
  it("formats semantic tool summaries from JSON input", () => {
    expect(summarizeToolUse("read", '{"path":"README.md"}')).toBe("Read: README.md");
  });

  it("falls back to raw input when JSON parsing fails", () => {
    expect(summarizeToolUse("bash", "git status")).toBe("Bash");
  });
});

describe("buildSearchExcerpt", () => {
  it("extracts a compact excerpt around the active match", () => {
    const message: Message = {
      id: "m1",
      role: "assistant",
      content: [{ type: "text", text: "The search target is inside this long assistant reply." }],
    };

    expect(buildSearchExcerpt(message, "target")).toContain("search target is inside");
  });
});

describe("extractProgressLines", () => {
  it("pulls the latest meaningful progress steps from reasoning text", () => {
    expect(
      extractProgressLines(
        [
          "Let me inspect the current TUI structure.",
          "",
          "- I should check how reasoning and tool events render.",
          "- Then I can adjust the live progress UI.",
        ].join("\n"),
      ),
    ).toEqual([
      "Let me inspect the current TUI structure.",
      "I should check how reasoning and tool events render.",
      "Then I can adjust the live progress UI.",
    ]);
  });
});

describe("buildCodexTimelineState", () => {
  it("materializes turn items and completion state from thread events", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "thread.started", thread_id: "thread_1" },
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.started",
          turn_id: "turn_1",
          item: { id: "reason_1", type: "reasoning", text: "Inspecting the repo structure." },
        },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "msg_1", type: "agent_message", text: "Here is the result." },
        },
        { type: "turn.completed", turn_id: "turn_1", stop_reason: "stop" },
      ],
      liveStatus: { isLoading: false },
      messages: [{ id: "user_1", role: "user", text: "compare codex and jarvis" }],
    });

    expect(state.blocks[0]?.id).toBe("user:user_1");
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]?.turnNumber).toBe(1);
    expect(state.turns[0]?.statusText).toBe("completed");
    expect(state.turns[0]?.items.map((item) => item.kind)).toEqual(["reasoning", "agent_message"]);
    expect(state.searchDocuments.map((doc) => doc.id)).toContain("user:user_1");
  });

  it("attaches live progress to the active turn while loading", () => {
    const state = buildCodexTimelineState({
      events: [{ type: "turn.started", turn_id: "turn_live" }],
      liveStatus: {
        isLoading: true,
        elapsedMs: 12_000,
        verb: "Thinking",
        status: "waiting for the model response",
        details: ["Requested the next turn"],
        running: "bash",
        completed: ["read_file"],
        tokenCount: 14,
      },
      messages: [],
    });

    const progress = state.turns[0]?.items.at(-1);
    expect(progress?.kind).toBe("progress");
    expect(state.turns[0]?.statsText).toBe("12s · ↓14 tokens");
    if (progress?.kind === "progress") {
      expect(progress.label).toBe("Using Bash");
      expect(progress.elapsedText).toBe("12s · ↓14 tokens");
      expect(progress.lines).toContain("waiting for the model response");
      expect(progress.lines).toContain("Requested the next turn");
      expect(progress.lines).toContain("Done: read_file");
      expect(progress.lines).toContain("Running: bash");
    }
  });

  it("uses a product phase label instead of freeform reasoning text", () => {
    const state = buildCodexTimelineState({
      events: [{ type: "turn.started", turn_id: "turn_live" }],
      liveStatus: {
        isLoading: true,
        elapsedMs: 9_000,
        verb: "Inspecting workspace carefully",
        tokenCount: 32,
      },
      messages: [],
    });

    const progress = state.turns[0]?.items.at(-1);
    expect(progress?.kind).toBe("progress");
    if (progress?.kind === "progress") {
      expect(progress.label).toBe("Concocting…");
    }
  });

  it("preserves turn-level elapsed and token stats after completion", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "msg_1", type: "agent_message", text: "Done." },
        },
        { type: "turn.completed", turn_id: "turn_1", stop_reason: "stop" },
      ],
      liveStatus: { isLoading: false },
      messages: [],
      turnSnapshots: [{ turnId: "turn_1", elapsedMs: 8_000, tokenCount: 168 }],
    });

    expect(state.turns[0]?.statsText).toBe("8s · ↓168 tokens");
  });

  it("normalizes completed stop reasons into a cleaner completed label", () => {
    const completed = buildCodexTimelineState({
      events: [{ type: "turn.completed", turn_id: "turn_done", stop_reason: "completed" }],
      liveStatus: { isLoading: false },
      messages: [],
    });

    const stopped = buildCodexTimelineState({
      events: [{ type: "turn.completed", turn_id: "turn_stop", stop_reason: "stop" }],
      liveStatus: { isLoading: false },
      messages: [],
    });

    expect(completed.turns[0]?.statusText).toBe("completed");
    expect(stopped.turns[0]?.statusText).toBe("completed");
  });

  it("adds a visible error card when a turn fails", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_fail" },
        {
          type: "turn.failed",
          turn_id: "turn_fail",
          error: { message: "Provider request timed out" },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    const errorItem = state.turns[0]?.items.find((item) => item.kind === "error");
    expect(errorItem?.kind).toBe("error");
    if (errorItem?.kind === "error") {
      expect(errorItem.label).toBe("Run failed");
      expect(errorItem.text).toContain("timed out");
    }
  });

  it("adapts task snapshots into codex-style todo cards and search documents", () => {
    const state = buildCodexTimelineState({
      events: [{ type: "turn.started", turn_id: "turn_tasks" }],
      liveStatus: { isLoading: false },
      messages: [],
      taskSnapshots: [
        {
          turnId: "turn_tasks",
          sourceId: "task_snapshot_turn_tasks",
          counts: { pending: 1, in_progress: 1, completed: 2 },
          tasks: [
            { id: "t1", subject: "Inspect codex timeline", status: "in_progress" },
            { id: "t2", subject: "Wire search docs", status: "pending" },
            { id: "t3", subject: "Replay the UI", status: "completed" },
          ],
        },
      ],
    });

    const todo = state.turns[0]?.items.find((item) => item.kind === "todo_list");
    expect(todo?.kind).toBe("todo_list");
    if (todo?.kind === "todo_list") {
      expect(todo.summary).toBe("1 active | 1 pending | 2 done");
      expect(todo.lines).toContain("~ Inspect codex timeline");
      expect(todo.lines).toContain("- Wire search docs");
      expect(todo.lines).toContain("x Replay the UI");
      expect(todo.collapsedLines).toEqual(["~ Inspect codex timeline", "- Wire search docs"]);
      expect(todo.overflowCount).toBe(1);
    }

    const todoDoc = state.searchDocuments.find((doc) => doc.id === "item:turn_tasks:task_snapshot_turn_tasks");
    expect(todoDoc?.text).toContain("Wire search docs");
  });

  it("formats tool calls as codex-style workflow cards", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_tools" },
        {
          type: "item.completed",
          turn_id: "turn_tools",
          item: {
            id: "tool_1",
            type: "tool_call",
            tool_name: "read",
            status: "completed",
            arguments: { path: "README.md" },
            result: "Loaded README",
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    const tool = state.turns[0]?.items.find((item) => item.kind === "tool_call");
    expect(tool?.kind).toBe("tool_call");
    if (tool?.kind === "tool_call") {
      expect(tool.label).toBe("Read");
      expect(tool.statusLabel).toBe("done");
      expect(tool.summary).toBe("README.md");
      expect(tool.collapsedDetail).toBe("README.md");
      expect(tool.resultText).toContain("Loaded README");
    }
  });

  it("omits failed tool calls from the codex timeline view", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_tools" },
        {
          type: "item.completed",
          turn_id: "turn_tools",
          item: {
            id: "tool_1",
            type: "tool_call",
            tool_name: "read_file",
            status: "failed",
            arguments: { path: "missing.txt" },
            error: "File not found: missing.txt",
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    expect(state.turns[0]?.items).toHaveLength(0);
  });

  it("hides failed tool calls from the codex timeline", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_tools" },
        {
          type: "item.completed",
          turn_id: "turn_tools",
          item: {
            id: "tool_failed",
            type: "tool_call",
            tool_name: "grep",
            status: "failed",
            arguments: { pattern: "AgentsPanel", path: "/tmp/src" },
            error: "Cannot access path",
          },
        },
        {
          type: "item.completed",
          turn_id: "turn_tools",
          item: {
            id: "tool_done",
            type: "tool_call",
            tool_name: "bash",
            status: "completed",
            arguments: { command: "cat package.json" },
            result: "ok",
          },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [],
    });

    expect(state.turns[0]?.items.map((item) => item.id)).toEqual(["tool_done"]);
    expect(state.searchDocuments.map((doc) => doc.id)).toContain("item:turn_tools:tool_done");
    expect(state.searchDocuments.map((doc) => doc.id)).not.toContain("item:turn_tools:tool_failed");
  });

  it("does not duplicate agent replies that already exist in turn events", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "reason_1", type: "reasoning", text: "I should answer in Chinese." },
        },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "msg_1", type: "agent_message", text: "我是 Jarvis，本地 AI 编程助手。" },
        },
        { type: "turn.completed", turn_id: "turn_1", stop_reason: "stop" },
      ],
      liveStatus: { isLoading: false },
      messages: [
        { id: "user_1", role: "user", text: "你是谁" },
        { id: "assistant_1", role: "assistant", text: "I should answer in Chinese." },
        { id: "assistant_2", role: "assistant", text: "我是 Jarvis，本地 AI 编程助手。" },
      ],
    });

    expect(state.blocks.map((block) => block.kind)).toEqual(["user_message", "turn"]);
  });

  it("deduplicates plain assistant blocks when final text only differs slightly from the turn answer", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: {
            id: "msg_1",
            type: "agent_message",
            text: "I can search files, edit code, and run shell commands in the current project.",
          },
        },
        { type: "turn.completed", turn_id: "turn_1", stop_reason: "stop" },
      ],
      liveStatus: { isLoading: false },
      messages: [
        { id: "user_1", role: "user", text: "what can you do" },
        {
          id: "assistant_1",
          role: "assistant",
          text: "I can search files, edit code, and run shell commands in the current project",
        },
      ],
    });

    expect(state.blocks.map((block) => block.kind)).toEqual(["user_message", "turn"]);
  });

  it("skips empty assistant content in codex timeline blocks", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_1" },
        {
          type: "item.completed",
          turn_id: "turn_1",
          item: { id: "msg_1", type: "agent_message", text: "   " },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [
        { id: "user_1", role: "user", text: "hello" },
        { id: "assistant_1", role: "assistant", text: "   " },
      ],
    });

    expect(state.blocks.map((block) => block.kind)).toEqual(["user_message", "turn"]);
    expect(state.turns[0]?.items).toHaveLength(0);
  });

  it("deduplicates plain assistant errors when the failed turn already has an error card", () => {
    const state = buildCodexTimelineState({
      events: [
        { type: "turn.started", turn_id: "turn_fail" },
        {
          type: "turn.failed",
          turn_id: "turn_fail",
          error: { message: "Connection error." },
        },
      ],
      liveStatus: { isLoading: false },
      messages: [
        { id: "user_1", role: "user", text: "hello" },
        { id: "assistant_1", role: "assistant", text: "Error calling LLM after retries: Connection error." },
      ],
    });

    expect(state.blocks.map((block) => block.kind)).toEqual(["user_message", "turn"]);
  });
});

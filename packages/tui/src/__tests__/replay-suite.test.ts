import { describe, expect, it } from "vitest";
import {
  buildFinalizeTimeoutPhaseDiagnosticScript,
  buildHistoryDriftDuringAnswerScript,
  buildHistoryDriftDuringLongAnswerTailScript,
  buildHistoryDriftDuringToolsScript,
  buildLongAnswerPrompt,
  buildNoProgressPhaseDiagnosticScript,
  buildRealToolHeavyPrompt,
  buildSelectionDuringToolsScript,
  buildToolHeavyFinalizeTimeoutPrompt,
  buildToolHeavyFinalizeTimeoutScript,
  buildToolHeavyNoProgressPrompt,
  buildToolHeavyNoProgressScript,
  buildToolHeavyPrompt,
} from "../replay-suite.js";

describe("replay-suite scenarios", () => {
  it("builds a history-drift script that pages up during a tool-heavy run", () => {
    const script = buildHistoryDriftDuringToolsScript();

    expect(script.some((action) => action.type === "key" && action.key === "pageup")).toBe(true);
    expect(script.some((action) => action.type === "wait" && action.ms >= 2000)).toBe(true);
  });

  it("builds a selection script that creates a selection during a tool-heavy run", () => {
    const script = buildSelectionDuringToolsScript();
    const selectAction = script.find((action) => action.type === "select");

    expect(selectAction).toBeDefined();
    expect(selectAction && selectAction.type === "select" ? selectAction.start.row : 0).toBeGreaterThan(0);
  });

  it("builds an answer-stream drift script that pages up after tool output", () => {
    const script = buildHistoryDriftDuringAnswerScript();

    expect(script.some((action) => action.type === "wait" && action.ms >= 3000)).toBe(true);
    expect(script.some((action) => action.type === "key" && action.key === "pageup")).toBe(true);
  });

  it("builds a long-tail answer drift script that keeps streaming after pageup", () => {
    const script = buildHistoryDriftDuringLongAnswerTailScript();

    expect(script.some((action) => action.type === "wait" && action.ms >= 5000)).toBe(true);
    expect(script.some((action) => action.type === "wait" && action.ms >= 3000)).toBe(true);
    expect(script.some((action) => action.type === "key" && action.key === "pageup")).toBe(true);
  });

  it("builds a finalize-timeout phase diagnostic script that waits for the synthetic stop", () => {
    const script = buildFinalizeTimeoutPhaseDiagnosticScript();

    expect(script.some((action) => action.type === "wait" && action.ms >= 2500)).toBe(true);
    expect(script.some((action) => action.type === "key" && action.key === "pageup")).toBe(false);
  });

  it("builds a no-progress phase diagnostic script that waits for the synthetic stop", () => {
    const script = buildNoProgressPhaseDiagnosticScript();

    expect(script.some((action) => action.type === "wait" && action.ms >= 2000)).toBe(true);
    expect(script.some((action) => action.type === "select")).toBe(false);
  });

  it("builds a tool-heavy finalize-timeout script that waits through the post-tool finalize tail", () => {
    const script = buildToolHeavyFinalizeTimeoutScript();

    expect(script.some((action) => action.type === "wait" && action.ms >= 3500)).toBe(true);
    expect(script.some((action) => action.type === "wait" && action.ms >= 2000)).toBe(true);
  });

  it("builds a tool-heavy no-progress script that waits through the post-tool stall window", () => {
    const script = buildToolHeavyNoProgressScript();

    expect(script.some((action) => action.type === "wait" && action.ms >= 3000)).toBe(true);
    expect(script.some((action) => action.type === "wait" && action.ms >= 1500)).toBe(true);
  });

  it("builds a tool-heavy prompt that nudges read-only tool usage", () => {
    const prompt = buildToolHeavyPrompt();

    expect(prompt).toContain("read-only tools");
    expect(prompt).toContain("shell search commands");
  });

  it("builds a real-app tool-heavy prompt that stays read-only and bounded", () => {
    const prompt = buildRealToolHeavyPrompt();

    expect(prompt).toContain("read-only tools");
    expect(prompt).toContain("Do not write files");
    expect(prompt).toContain("3 bullet points");
  });

  it("builds a long-answer prompt for real app answer-stream drift runs", () => {
    const prompt = buildLongAnswerPrompt();

    expect(prompt).toContain("very long answer");
    expect(prompt).toContain("multiple sections");
    expect(prompt).toContain("Do not use tools");
  });

  it("builds a tool-heavy finalize-timeout prompt that asks for read-only investigation before a final answer", () => {
    const prompt = buildToolHeavyFinalizeTimeoutPrompt();

    expect(prompt).toContain("read-only tools");
    expect(prompt).toContain("final answer");
    expect(prompt).toContain("tool-heavy");
  });

  it("builds a tool-heavy no-progress prompt that asks for read-only investigation before diagnosing a stall", () => {
    const prompt = buildToolHeavyNoProgressPrompt();

    expect(prompt).toContain("read-only tools");
    expect(prompt).toContain("tool-heavy");
    expect(prompt).toContain("stall");
  });
});

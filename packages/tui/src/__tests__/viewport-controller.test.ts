import { describe, expect, it } from "vitest";
import {
  createViewportState,
  reduceViewportState,
  type ViewportAction,
} from "../vendor/ui/viewport-controller.js";

function applyActions(actions: ViewportAction[]) {
  return actions.reduce(reduceViewportState, createViewportState());
}

describe("viewport controller", () => {
  it("enters history mode when the user scrolls away from live output", () => {
    const state = applyActions([{ type: "user_scrolled" }]);

    expect(state.mode).toBe("history");
    expect(state.followOutput).toBe(false);
  });

  it("elevates selection above history and follow", () => {
    const state = applyActions([
      { type: "user_scrolled" },
      { type: "selection_changed", hasSelection: true },
    ]);

    expect(state.mode).toBe("selection");
    expect(state.followOutput).toBe(false);
  });

  it("does not auto-resume follow when selection clears", () => {
    const state = applyActions([
      { type: "user_scrolled" },
      { type: "selection_changed", hasSelection: true },
      { type: "selection_changed", hasSelection: false },
    ]);

    expect(state.mode).toBe("history");
    expect(state.followOutput).toBe(false);
  });

  it("resumes follow only on explicit bottom action without selection", () => {
    const state = applyActions([
      { type: "user_scrolled" },
      { type: "bottom_action" },
    ]);

    expect(state.mode).toBe("following");
    expect(state.followOutput).toBe(true);
  });

  it("keeps selection mode on bottom action while selection is active", () => {
    const state = applyActions([
      { type: "selection_changed", hasSelection: true },
      { type: "bottom_action" },
    ]);

    expect(state.mode).toBe("selection");
    expect(state.followOutput).toBe(false);
  });

  it("tracks scroll draining without changing history mode", () => {
    const state = applyActions([
      { type: "user_scrolled" },
      { type: "scroll_draining_changed", scrollDraining: true },
    ]);

    expect(state.mode).toBe("history");
    expect(state.scrollDraining).toBe(true);
  });
});

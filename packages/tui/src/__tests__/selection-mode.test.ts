import { describe, expect, it } from "vitest";
import {
  getViewportMode,
  shouldAutoResumeFollow,
  shouldResumeLiveOutputFromBottomAction,
} from "../vendor/ui/viewport-mode.js";
import { shouldTranslateSelectionOnFollow } from "../vendor/ink-renderer/selection-follow.js";

describe("selection mode viewport rules", () => {
  it("elevates selection above follow/history states", () => {
    expect(
      getViewportMode({
        followOutput: true,
        hasSelection: true,
        interactivePromptActive: false,
      }),
    ).toBe("selection");
  });

  it("does not auto-resume follow while a selection exists", () => {
    expect(
      shouldAutoResumeFollow({
        followOutput: false,
        hasSelection: true,
        interactivePromptActive: false,
        isLoading: false,
        remainingScrollDistance: 0,
      }),
    ).toBe(false);
  });

  it("does not implicitly resume live follow in history mode", () => {
    expect(
      shouldAutoResumeFollow({
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        isLoading: false,
        remainingScrollDistance: 0,
      }),
    ).toBe(false);
  });

  it("only allows explicit bottom resume when selection mode is inactive", () => {
    expect(shouldResumeLiveOutputFromBottomAction(true)).toBe(false);
    expect(shouldResumeLiveOutputFromBottomAction(false)).toBe(true);
  });
});

describe("selection follow translation guard", () => {
  it("does not translate the selection during follow while selection mode is active", () => {
    expect(
      shouldTranslateSelectionOnFollow({
        selectionModeActive: true,
        hasAnchor: true,
        anchorRow: 6,
        focusRow: 8,
        viewportTop: 4,
        viewportBottom: 20,
      }),
    ).toBe(false);
  });

  it("only translates when both endpoints remain in the scroll viewport", () => {
    expect(
      shouldTranslateSelectionOnFollow({
        selectionModeActive: false,
        hasAnchor: true,
        anchorRow: 6,
        focusRow: 21,
        viewportTop: 4,
        viewportBottom: 20,
      }),
    ).toBe(false);
  });
});

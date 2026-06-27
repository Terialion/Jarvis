import { describe, expect, it } from "vitest";
import {
  clearScrollChrome,
  createScrollChromeState,
  formatJumpToBottomLabel,
  recordScrollChromeSnapshot,
  recordScrollChromeTranscriptMutation,
  shouldShowJumpToBottomPill,
} from "../vendor/ui/scroll-chrome.js";

describe("scroll chrome", () => {
  it("records a baseline when the user leaves the bottom", () => {
    const state = recordScrollChromeSnapshot(createScrollChromeState(), {
      mode: "history",
      itemCount: 8,
      scrollHeight: 120,
      viewportHeight: 30,
      scrollTop: 40,
    });

    expect(state).toMatchObject({
      active: true,
      baselineItemCount: 8,
      baselineScrollHeight: 120,
      unseenCount: 0,
    });
    expect(shouldShowJumpToBottomPill(state)).toBe(true);
  });

  it("tracks unseen output without asking the viewport to follow", () => {
    const state = recordScrollChromeSnapshot(createScrollChromeState(), {
      mode: "history",
      itemCount: 8,
      scrollHeight: 120,
      viewportHeight: 30,
      scrollTop: 40,
    });

    const next = recordScrollChromeTranscriptMutation(state, {
      mode: "history",
      itemCount: 11,
      scrollHeight: 180,
    });

    expect(next).toMatchObject({
      active: true,
      unseenCount: 3,
      shouldRequestFollow: false,
    });
    expect(formatJumpToBottomLabel(next)).toBe("3 new messages | End to jump");
  });

  it("treats selection mode as a hard passive mode", () => {
    const state = recordScrollChromeTranscriptMutation(
      recordScrollChromeSnapshot(createScrollChromeState(), {
        mode: "selection",
        itemCount: 5,
        scrollHeight: 80,
        viewportHeight: 25,
        scrollTop: 20,
      }),
      {
        mode: "selection",
        itemCount: 7,
        scrollHeight: 120,
      },
    );

    expect(state.unseenCount).toBe(2);
    expect(state.shouldRequestFollow).toBe(false);
    expect(shouldShowJumpToBottomPill(state)).toBe(true);
  });

  it("clears the pill when live follow is explicitly restored", () => {
    const state = recordScrollChromeSnapshot(createScrollChromeState(), {
      mode: "history",
      itemCount: 8,
      scrollHeight: 120,
      viewportHeight: 30,
      scrollTop: 40,
    });

    expect(shouldShowJumpToBottomPill(clearScrollChrome(state))).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import {
  isUserViewportScrollMutationSource,
  resolveViewportTopForFollowState,
  shouldAutoScrollToBottomOnContentUpdate,
} from "../vendor/ui/viewport-mode.js";

describe("viewport-mode follow guards", () => {
  it("does not treat stale sticky state as live follow once followOutput is off", () => {
    expect(
      resolveViewportTopForFollowState({
        followOutput: false,
        scrollTop: 42,
        scrollHeight: 200,
        viewportHeight: 40,
        pendingDelta: 0,
      }),
    ).toBe(42);
  });

  it("pins to the real bottom only while followOutput is on", () => {
    expect(
      resolveViewportTopForFollowState({
        followOutput: true,
        scrollTop: 42,
        scrollHeight: 200,
        viewportHeight: 40,
        pendingDelta: 0,
      }),
    ).toBe(160);
  });

  it("uses the observed scroll delta once a live viewport has started scrolling away", () => {
    expect(
      resolveViewportTopForFollowState({
        followOutput: true,
        scrollTop: 160,
        scrollHeight: 240,
        viewportHeight: 40,
        pendingDelta: -24,
      }),
    ).toBe(136);
  });

  it("refuses content-update auto-scroll whenever live follow is already broken", () => {
    expect(
      shouldAutoScrollToBottomOnContentUpdate({
        followOutput: false,
        hasSelection: false,
        interactivePromptActive: false,
        scrollDraining: false,
        remainingScrollDistance: 0,
      }),
    ).toBe(false);
  });

  it("does not treat programmatic live-follow scrolls as user scroll draining", () => {
    expect(isUserViewportScrollMutationSource("imperative_scroll_bottom")).toBe(false);
    expect(isUserViewportScrollMutationSource("render_follow")).toBe(false);
    expect(isUserViewportScrollMutationSource("imperative_scroll_by")).toBe(true);
    expect(isUserViewportScrollMutationSource("imperative_scroll_to")).toBe(true);
  });
});
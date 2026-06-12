import { describe, expect, it } from "vitest";
import {
  computeAutoFollowState,
  shouldApplyMountedRangeClamp,
  shouldPersistScrollTopAfterClamp,
} from "../vendor/ink-renderer/render-node-to-output.js";

describe("computeAutoFollowState", () => {
  it("does not auto-follow after manual scroll broke sticky mode", () => {
    const result = computeAutoFollowState({
      scrollTopBeforeFollow: 80,
      stickyState: false,
      stickyAttribute: false,
      selectionLocked: false,
      followDisabled: false,
      prevScrollHeight: 120,
      prevViewportHeight: 40,
      scrollHeight: 140,
      viewportHeight: 40,
      pendingDelta: undefined,
    });

    expect(result.shouldFollow).toBe(false);
    expect(result.nextScrollTop).toBe(80);
    expect(result.restoreSticky).toBe(false);
    expect(result.followDelta).toBe(0);
  });

  it("keeps following when sticky mode is explicitly active", () => {
    const result = computeAutoFollowState({
      scrollTopBeforeFollow: 80,
      stickyState: true,
      stickyAttribute: false,
      selectionLocked: false,
      followDisabled: false,
      prevScrollHeight: 120,
      prevViewportHeight: 40,
      scrollHeight: 140,
      viewportHeight: 40,
      pendingDelta: undefined,
    });

    expect(result.shouldFollow).toBe(true);
    expect(result.nextScrollTop).toBe(100);
    expect(result.followDelta).toBe(20);
  });

  it("does not auto-follow while selection mode is locking the viewport", () => {
    const result = computeAutoFollowState({
      scrollTopBeforeFollow: 80,
      stickyState: true,
      stickyAttribute: true,
      selectionLocked: true,
      followDisabled: false,
      prevScrollHeight: 120,
      prevViewportHeight: 40,
      scrollHeight: 140,
      viewportHeight: 40,
      pendingDelta: undefined,
    });

    expect(result.shouldFollow).toBe(false);
    expect(result.nextScrollTop).toBe(80);
    expect(result.followDelta).toBe(0);
  });

  it("does not persist a transient max-scroll clamp while browsing history", () => {
    expect(
      shouldPersistScrollTopAfterClamp({
        currentScrollTop: 180,
        clampedToMaxScroll: 0,
        pendingDelta: undefined,
        followedThisFrame: false,
      }),
    ).toBe(false);
  });

  it("does not apply mounted-range clamp while passively browsing history", () => {
    expect(
      shouldApplyMountedRangeClamp({
        pendingDelta: undefined,
        followedThisFrame: false,
      }),
    ).toBe(false);

    expect(
      shouldApplyMountedRangeClamp({
        pendingDelta: 0,
        followedThisFrame: false,
      }),
    ).toBe(false);
  });

  it("does not auto-follow while follow is explicitly disabled", () => {
    const result = computeAutoFollowState({
      scrollTopBeforeFollow: 80,
      stickyState: true,
      stickyAttribute: true,
      selectionLocked: false,
      followDisabled: true,
      prevScrollHeight: 120,
      prevViewportHeight: 40,
      scrollHeight: 140,
      viewportHeight: 40,
      pendingDelta: undefined,
    });

    expect(result.shouldFollow).toBe(false);
    expect(result.nextScrollTop).toBe(80);
  });

  it("still persists scrollTop changes caused by real follow or drain", () => {
    expect(
      shouldPersistScrollTopAfterClamp({
        currentScrollTop: 80,
        clampedToMaxScroll: 100,
        pendingDelta: undefined,
        followedThisFrame: true,
      }),
    ).toBe(true);

    expect(
      shouldPersistScrollTopAfterClamp({
        currentScrollTop: 80,
        clampedToMaxScroll: 92,
        pendingDelta: 12,
        followedThisFrame: false,
      }),
    ).toBe(true);

    expect(
      shouldApplyMountedRangeClamp({
        pendingDelta: 12,
        followedThisFrame: false,
      }),
    ).toBe(true);

    expect(
      shouldApplyMountedRangeClamp({
        pendingDelta: undefined,
        followedThisFrame: true,
      }),
    ).toBe(true);
  });
});

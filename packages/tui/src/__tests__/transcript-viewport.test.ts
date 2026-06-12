import { describe, expect, it } from "vitest";
import {
  shouldExposeMountedRangeClamp,
  shouldRefreshViewportSnapshotAfterLayout,
} from "../vendor/ui/TranscriptViewport.js";

describe("TranscriptViewport passive history guards", () => {
  it("only exposes mounted clamp during real follow or real scroll drain", () => {
    expect(
      shouldExposeMountedRangeClamp({
        pendingDelta: 0,
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
      }),
    ).toBe(false);

    expect(
      shouldExposeMountedRangeClamp({
        pendingDelta: 0,
        followDisabled: false,
        selectionLocked: false,
        sticky: true,
      }),
    ).toBe(true);

    expect(
      shouldExposeMountedRangeClamp({
        pendingDelta: 6,
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
      }),
    ).toBe(true);
  });

  it("freezes layout-driven snapshot updates while passively browsing history", () => {
    expect(
      shouldRefreshViewportSnapshotAfterLayout({
        current: {
          scrollTop: 120,
          viewportHeight: 30,
          pendingDelta: 0,
        },
        next: {
          scrollTop: 0,
          viewportHeight: 18,
          pendingDelta: 0,
        },
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
      }),
    ).toBe(false);
  });

  it("still refreshes snapshot updates during active follow or active drain", () => {
    expect(
      shouldRefreshViewportSnapshotAfterLayout({
        current: {
          scrollTop: 120,
          viewportHeight: 30,
          pendingDelta: 0,
        },
        next: {
          scrollTop: 132,
          viewportHeight: 30,
          pendingDelta: 0,
        },
        followDisabled: false,
        selectionLocked: false,
        sticky: true,
      }),
    ).toBe(true);

    expect(
      shouldRefreshViewportSnapshotAfterLayout({
        current: {
          scrollTop: 120,
          viewportHeight: 30,
          pendingDelta: 8,
        },
        next: {
          scrollTop: 112,
          viewportHeight: 30,
          pendingDelta: 4,
        },
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
      }),
    ).toBe(true);
  });
});

import { describe, expect, it } from "vitest";
import {
  shouldExposeMountedRangeClamp,
  shouldPreservePassiveViewportScrollTop,
  shouldRefreshViewportSnapshotAfterLayout,
  shouldUpdatePassiveScrollAnchor,
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

  it("does not let render-time clamps replace the passive history anchor", () => {
    expect(
      shouldUpdatePassiveScrollAnchor({
        pendingDelta: 0,
        mutationSource: "render_persist_clamp",
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
      }),
    ).toBe(false);

    expect(
      shouldUpdatePassiveScrollAnchor({
        pendingDelta: 0,
        mutationSource: "render_persist_clamp",
        followDisabled: true,
        selectionLocked: true,
        sticky: false,
      }),
    ).toBe(false);

    expect(
      shouldUpdatePassiveScrollAnchor({
        pendingDelta: 0,
        mutationSource: "imperative_scroll_by",
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

  it("preserves the existing scrollTop while history mode is passively locked", () => {
    expect(
      shouldPreservePassiveViewportScrollTop({
        desiredScrollTop: 14,
        next: {
          scrollTop: 0,
          pendingDelta: 0,
        },
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
        maxScrollTop: 45,
      }),
    ).toBe(14);
  });

  it("does not imperatively restore scrollTop while selection mode is active", () => {
    expect(
      shouldPreservePassiveViewportScrollTop({
        desiredScrollTop: 14,
        next: {
          scrollTop: 0,
          pendingDelta: 0,
        },
        followDisabled: true,
        selectionLocked: true,
        sticky: false,
        maxScrollTop: 45,
      }),
    ).toBeNull();
  });

  it("does not persist a smaller scrollTop when measured height temporarily shrinks", () => {
    expect(
      shouldPreservePassiveViewportScrollTop({
        desiredScrollTop: 50,
        next: {
          scrollTop: 0,
          pendingDelta: 0,
        },
        followDisabled: true,
        selectionLocked: false,
        sticky: false,
        maxScrollTop: 18,
      }),
    ).toBeNull();
  });
});

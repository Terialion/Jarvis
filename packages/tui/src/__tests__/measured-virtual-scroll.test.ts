import { describe, expect, it } from "vitest";
import {
  buildMeasuredOffsets,
  computeMeasuredRange,
  getMeasuredOffsetsCached,
  pruneMeasuredHeightCache,
  scaleHeightCache,
} from "../vendor/ui/measured-virtual-scroll.js";

describe("measured virtual scroll helpers", () => {
  it("scales cached heights on terminal width changes", () => {
    const cache = new Map([
      ["a", 10],
      ["b", 20],
    ]);

    scaleHeightCache(cache, 100, 50);

    expect(cache.get("a")).toBe(20);
    expect(cache.get("b")).toBe(40);
  });

  it("builds offsets from measured heights with fallback estimates", () => {
    const itemKeys = ["a", "b", "c"];
    const cache = new Map([
      ["a", 4],
      ["c", 6],
    ]);

    const offsets = buildMeasuredOffsets({
      itemKeys,
      heightCache: cache,
      estimatedHeight: 3,
    });

    expect(offsets).toEqual([0, 4, 7]);
  });

  it("uses per-item estimated heights before measurement is available", () => {
    const itemKeys = ["a", "b", "c"];
    const cache = new Map<string, number>();
    const estimatedHeights = new Map([
      ["a", 3],
      ["b", 12],
      ["c", 5],
    ]);

    const offsets = buildMeasuredOffsets({
      itemKeys,
      heightCache: cache,
      estimatedHeight: 6,
      estimatedHeights,
    });

    expect(offsets).toEqual([0, 3, 15]);
  });

  it("computes a visible range around the viewport with overscan", () => {
    const itemKeys = ["a", "b", "c", "d", "e"];
    const cache = new Map([
      ["a", 4],
      ["b", 5],
      ["c", 5],
      ["d", 5],
      ["e", 5],
    ]);

    const range = computeMeasuredRange({
      itemKeys,
      heightCache: cache,
      estimatedHeight: 4,
      scrollTop: 5,
      viewportHeight: 7,
      overscan: 1,
      pendingDelta: 0,
    });

    expect(range.startIndex).toBe(0);
    expect(range.endIndex).toBe(4);
    expect(range.totalHeight).toBe(24);
  });

  it("extends the range toward pending scroll drain to avoid blank frames", () => {
    const itemKeys = ["a", "b", "c", "d", "e", "f"];
    const cache = new Map(itemKeys.map((key) => [key, 4]));

    const range = computeMeasuredRange({
      itemKeys,
      heightCache: cache,
      estimatedHeight: 4,
      scrollTop: 0,
      viewportHeight: 8,
      overscan: 0,
      pendingDelta: 8,
    });

    expect(range.endIndex).toBeGreaterThanOrEqual(4);
  });

  it("computes total height using item-specific fallback estimates", () => {
    const itemKeys = ["small", "large", "tail"];
    const estimatedHeights = new Map([
      ["small", 3],
      ["large", 20],
      ["tail", 4],
    ]);

    const range = computeMeasuredRange({
      itemKeys,
      heightCache: new Map(),
      estimatedHeight: 6,
      estimatedHeights,
      scrollTop: 0,
      viewportHeight: 10,
      overscan: 0,
      pendingDelta: 0,
    });

    expect(range.totalHeight).toBe(27);
    expect(range.endIndex).toBe(2);
  });

  it("invalidates cached offsets when item identities change with the same length", () => {
    const cache = new Map([
      ["a", 4],
      ["b", 6],
      ["x", 10],
      ["y", 12],
    ]);

    const first = getMeasuredOffsetsCached({
      cache: null,
      version: 1,
      itemKeys: ["a", "b"],
      heightCache: cache,
      estimatedHeight: 3,
    });
    const second = getMeasuredOffsetsCached({
      cache: first,
      version: 1,
      itemKeys: ["x", "y"],
      heightCache: cache,
      estimatedHeight: 3,
    });

    expect(first.offsets).toEqual([0, 4]);
    expect(second.offsets).toEqual([0, 10]);
  });

  it("prunes stale measured heights when transcript items are replaced", () => {
    const cache = new Map([
      ["a", 4],
      ["b", 6],
      ["c", 8],
    ]);

    const mutated = pruneMeasuredHeightCache(cache, ["a", "c"]);

    expect(mutated).toBe(true);
    expect(Array.from(cache.entries())).toEqual([
      ["a", 4],
      ["c", 8],
    ]);
  });
});

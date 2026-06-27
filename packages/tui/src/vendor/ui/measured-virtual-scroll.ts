export type MeasuredRangeInput = {
  itemKeys: readonly string[];
  heightCache: ReadonlyMap<string, number>;
  estimatedHeight: number;
  estimatedHeights?: ReadonlyMap<string, number>;
  scrollTop: number;
  viewportHeight: number;
  overscan: number;
  pendingDelta?: number;
  offsets?: readonly number[];
};

export type MeasuredRange = {
  startIndex: number;
  endIndex: number;
  totalHeight: number;
  offsets: number[];
};

export type MeasuredOffsetsCache = {
  offsets: number[];
  version: number;
  itemCount: number;
  signature: string;
};

function getEstimatedItemHeight(
  itemKey: string,
  heightCache: ReadonlyMap<string, number>,
  estimatedHeight: number,
  estimatedHeights?: ReadonlyMap<string, number>,
): number {
  return heightCache.get(itemKey) ?? estimatedHeights?.get(itemKey) ?? estimatedHeight;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function scaleHeightCache(
  heightCache: Map<string, number>,
  prevColumns: number,
  nextColumns: number,
): void {
  if (prevColumns <= 0 || nextColumns <= 0 || prevColumns === nextColumns) return;
  const ratio = prevColumns / nextColumns;
  for (const [key, height] of heightCache) {
    heightCache.set(key, Math.max(1, Math.round(height * ratio)));
  }
}

export function pruneMeasuredHeightCache(
  heightCache: Map<string, number>,
  liveKeys: readonly string[],
): boolean {
  const live = new Set(liveKeys);
  let mutated = false;
  for (const key of heightCache.keys()) {
    if (!live.has(key)) {
      heightCache.delete(key);
      mutated = true;
    }
  }
  return mutated;
}

export function buildMeasuredOffsets(input: {
  itemKeys: readonly string[];
  heightCache: ReadonlyMap<string, number>;
  estimatedHeight: number;
  estimatedHeights?: ReadonlyMap<string, number>;
}): number[] {
  const { itemKeys, heightCache, estimatedHeight, estimatedHeights } = input;
  const offsets: number[] = [];
  let offset = 0;
  for (const key of itemKeys) {
    offsets.push(offset);
    offset += getEstimatedItemHeight(key, heightCache, estimatedHeight, estimatedHeights);
  }
  return offsets;
}

export function getMeasuredOffsetsCached(input: {
  cache: MeasuredOffsetsCache | null;
  version: number;
  itemKeys: readonly string[];
  heightCache: ReadonlyMap<string, number>;
  estimatedHeight: number;
  estimatedHeights?: ReadonlyMap<string, number>;
}): MeasuredOffsetsCache {
  const { cache, version, itemKeys, heightCache, estimatedHeight, estimatedHeights } = input;
  const signature = itemKeys.join("\u0000");
  if (cache && cache.version === version && cache.itemCount === itemKeys.length && cache.signature === signature) {
    return cache;
  }

  return {
    offsets: buildMeasuredOffsets({ itemKeys, heightCache, estimatedHeight, estimatedHeights }),
    version,
    itemCount: itemKeys.length,
    signature,
  };
}

function findStartIndex(offsets: number[], totalHeight: number, scrollTop: number): number {
  if (offsets.length === 0) return 0;
  let lo = 0;
  let hi = offsets.length - 1;
  const target = clamp(scrollTop, 0, Math.max(0, totalHeight));
  while (lo < hi) {
    const mid = Math.floor((lo + hi + 1) / 2);
    if (offsets[mid]! <= target) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export function computeMeasuredRange(input: MeasuredRangeInput): MeasuredRange {
  const {
    itemKeys,
    heightCache,
    estimatedHeight,
    estimatedHeights,
    scrollTop,
    viewportHeight,
    overscan,
    pendingDelta = 0,
  } = input;
  const offsets = input.offsets
    ? [...input.offsets]
    : buildMeasuredOffsets({ itemKeys, heightCache, estimatedHeight, estimatedHeights });
  const totalHeight =
    itemKeys.length === 0
      ? 0
      : offsets[offsets.length - 1]! +
        getEstimatedItemHeight(
          itemKeys[itemKeys.length - 1]!,
          heightCache,
          estimatedHeight,
          estimatedHeights,
        );

  if (itemKeys.length === 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      totalHeight,
      offsets,
    };
  }

  const effectiveTop = Math.max(0, Math.min(scrollTop, scrollTop + Math.min(0, pendingDelta)));
  const effectiveBottom = Math.max(
    effectiveTop + viewportHeight,
    scrollTop + viewportHeight + Math.max(0, pendingDelta),
  );

  const start = findStartIndex(offsets, totalHeight, effectiveTop);
  let end = start;
  while (end < itemKeys.length) {
    const top = offsets[end]!;
    const bottom =
      top + getEstimatedItemHeight(itemKeys[end]!, heightCache, estimatedHeight, estimatedHeights);
    if (bottom >= effectiveBottom) break;
    end += 1;
  }

  return {
    startIndex: clamp(start - overscan, 0, itemKeys.length),
    endIndex: clamp(end + 1 + overscan, 0, itemKeys.length),
    totalHeight,
    offsets,
  };
}

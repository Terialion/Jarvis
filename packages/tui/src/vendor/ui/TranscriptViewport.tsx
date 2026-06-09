import { Box, ScrollBox, type DOMElement, type ScrollBoxHandle } from "../ink-renderer/index.js";
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  computeMeasuredRange,
  getMeasuredOffsetsCached,
  pruneMeasuredHeightCache,
  scaleHeightCache,
  type MeasuredOffsetsCache,
} from "./measured-virtual-scroll.js";

export type TranscriptItem = {
  id: string;
  estimatedHeight?: number;
  render: () => ReactNode;
};

export function TranscriptViewport({
  items,
  scrollRef,
  selectionLocked,
  followDisabled,
  onMetricsChange,
}: {
  items: TranscriptItem[];
  scrollRef: React.RefObject<ScrollBoxHandle | null>;
  selectionLocked?: boolean;
  followDisabled?: boolean;
  onMetricsChange?: (metrics: {
    scrollTop: number;
    viewportHeight: number;
    pendingDelta: number;
    clampMin?: number;
    clampMax?: number;
    totalHeight: number;
    startIndex: number;
    endIndex: number;
  }) => void;
}): ReactNode {
  const heightCacheRef = useRef(new Map<string, number>());
  const itemRefs = useRef(new Map<string, DOMElement | null>());
  const [measurementVersion, setMeasurementVersion] = useState(0);
  const [columns, setColumns] = useState(process.stdout.columns ?? 80);
  const [scrollSnapshot, setScrollSnapshot] = useState(() => ({
    scrollTop: scrollRef.current?.getScrollTop() ?? 0,
    viewportHeight: scrollRef.current?.getViewportHeight() ?? 0,
    pendingDelta: scrollRef.current?.getPendingDelta() ?? 0,
  }));
  const offsetsCacheRef = useRef<MeasuredOffsetsCache | null>(null);

  const itemKeys = useMemo(() => items.map((item) => item.id), [items]);
  const offsetsCache = useMemo(() => {
    const nextCache = getMeasuredOffsetsCached({
      cache: offsetsCacheRef.current,
      version: measurementVersion,
      itemKeys,
      heightCache: heightCacheRef.current,
      estimatedHeight: 6,
    });
    offsetsCacheRef.current = nextCache;
    return nextCache;
  }, [itemKeys, measurementVersion]);

  useEffect(() => {
    const liveKeys = new Set(itemKeys);
    const mutated = pruneMeasuredHeightCache(heightCacheRef.current, itemKeys);

    for (const key of itemRefs.current.keys()) {
      if (!liveKeys.has(key)) {
        itemRefs.current.delete(key);
      }
    }

    if (mutated) {
      setMeasurementVersion((value) => value + 1);
    }
  }, [itemKeys]);

  useEffect(() => {
    const handle = scrollRef.current;
    if (!handle) return;
    setScrollSnapshot({
      scrollTop: handle.getScrollTop(),
      viewportHeight: handle.getViewportHeight(),
      pendingDelta: handle.getPendingDelta(),
    });
    return handle.subscribe(() => {
      setScrollSnapshot({
        scrollTop: handle.getScrollTop(),
        viewportHeight: handle.getViewportHeight(),
        pendingDelta: handle.getPendingDelta(),
      });
    });
  }, [scrollRef]);

  const range = useMemo(
    () =>
      computeMeasuredRange({
        itemKeys,
        heightCache: heightCacheRef.current,
        estimatedHeight: 6,
        scrollTop: scrollSnapshot.scrollTop,
        viewportHeight: scrollSnapshot.viewportHeight,
        overscan: 2,
        pendingDelta: scrollSnapshot.pendingDelta,
        offsets: offsetsCache.offsets,
      }),
    [itemKeys, offsetsCache.offsets, scrollSnapshot],
  );

  const topPad = range.startIndex > 0 ? range.offsets[range.startIndex] ?? 0 : 0;
  const renderedHeight = range.endIndex > range.startIndex
    ? (range.offsets[range.endIndex - 1] ?? 0) +
      (heightCacheRef.current.get(items[range.endIndex - 1]?.id ?? "") ??
        items[range.endIndex - 1]?.estimatedHeight ??
        6) -
      topPad
    : 0;
  const bottomPad = Math.max(0, range.totalHeight - topPad - renderedHeight);
  const visibleItems = items.slice(range.startIndex, range.endIndex);

  const setItemRef = useCallback((id: string, el: DOMElement | null) => {
    itemRefs.current.set(id, el);
  }, []);

  useLayoutEffect(() => {
    const nextColumns = process.stdout.columns ?? 80;
    if (nextColumns !== columns) {
      scaleHeightCache(heightCacheRef.current, columns, nextColumns);
      setColumns(nextColumns);
    }

    let mutated = false;
    for (const item of visibleItems) {
      const el = itemRefs.current.get(item.id);
      const nextHeight = Math.max(1, Math.ceil(el?.yogaNode?.getComputedHeight() ?? item.estimatedHeight ?? 6));
      if (heightCacheRef.current.get(item.id) !== nextHeight) {
        heightCacheRef.current.set(item.id, nextHeight);
        mutated = true;
      }
    }

    const offsets = offsetsCacheRef.current?.offsets ?? [];
    const clampMin = range.startIndex < offsets.length ? offsets[range.startIndex] : undefined;
    const clampMax =
      range.endIndex > 0 && range.endIndex - 1 < offsets.length
        ? (offsets[range.endIndex - 1] ?? 0) +
          (heightCacheRef.current.get(items[range.endIndex - 1]?.id ?? "") ??
            items[range.endIndex - 1]?.estimatedHeight ??
            6)
        : undefined;
    const handle = scrollRef.current;
    handle?.setClampBounds(clampMin, clampMax);

    if (handle) {
      const nextSnapshot = {
        scrollTop: handle.getScrollTop(),
        viewportHeight: handle.getViewportHeight(),
        pendingDelta: handle.getPendingDelta(),
      };
      setScrollSnapshot((current) =>
        current.scrollTop === nextSnapshot.scrollTop &&
        current.viewportHeight === nextSnapshot.viewportHeight &&
        current.pendingDelta === nextSnapshot.pendingDelta
          ? current
          : nextSnapshot,
      );
    }

    onMetricsChange?.({
      scrollTop: handle?.getScrollTop() ?? 0,
      viewportHeight: handle?.getViewportHeight() ?? 0,
      pendingDelta: handle?.getPendingDelta() ?? 0,
      clampMin,
      clampMax,
      totalHeight: range.totalHeight,
      startIndex: range.startIndex,
      endIndex: range.endIndex,
    });

    if (mutated) {
      setMeasurementVersion((value) => value + 1);
    }
  }, [columns, itemKeys, items, onMetricsChange, range.endIndex, range.startIndex, range.totalHeight, scrollRef, visibleItems]);

  return (
    <ScrollBox
      ref={scrollRef}
      flexDirection="column"
      flexGrow={1}
      stickyScroll={false}
      selectionLocked={selectionLocked}
      followDisabled={followDisabled}
    >
      <Box flexDirection="column" width="100%">
        {topPad > 0 ? <Box height={topPad} /> : null}
        {visibleItems.map((item) => (
          <Box key={item.id} ref={(el) => setItemRef(item.id, el)} flexDirection="column" width="100%">
            {item.render()}
          </Box>
        ))}
        {bottomPad > 0 ? <Box height={bottomPad} /> : null}
      </Box>
    </ScrollBox>
  );
}

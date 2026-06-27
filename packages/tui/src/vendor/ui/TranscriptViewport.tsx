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

export function shouldExposeMountedRangeClamp(input: {
  pendingDelta: number;
  followDisabled: boolean;
  selectionLocked: boolean;
  sticky: boolean;
}): boolean {
  const { pendingDelta, followDisabled, selectionLocked, sticky } = input;
  if (pendingDelta !== 0) return true;
  if (selectionLocked) return false;
  if (followDisabled) return false;
  return sticky;
}

export function shouldRefreshViewportSnapshotAfterLayout(input: {
  current: {
    scrollTop: number;
    viewportHeight: number;
    pendingDelta: number;
  };
  next: {
    scrollTop: number;
    viewportHeight: number;
    pendingDelta: number;
  };
  followDisabled: boolean;
  selectionLocked: boolean;
  sticky: boolean;
}): boolean {
  const { current, next, followDisabled, selectionLocked, sticky } = input;
  const passiveViewportLocked = (followDisabled || selectionLocked) && !sticky && next.pendingDelta === 0;
  if (passiveViewportLocked) {
    return false;
  }

  return (
    current.scrollTop !== next.scrollTop ||
    current.viewportHeight !== next.viewportHeight ||
    current.pendingDelta !== next.pendingDelta
  );
}

export function shouldUpdatePassiveScrollAnchor(input: {
  pendingDelta: number;
  mutationSource?: string;
  followDisabled: boolean;
  selectionLocked: boolean;
  sticky: boolean;
}): boolean {
  const { pendingDelta, mutationSource, followDisabled, selectionLocked, sticky } = input;
  if (pendingDelta !== 0) {
    return false;
  }

  const passiveViewportLocked = (followDisabled || selectionLocked) && !sticky;
  if (!passiveViewportLocked) {
    return true;
  }

  return mutationSource === "imperative_scroll_by" || mutationSource === "imperative_scroll_to";
}

export function shouldPreservePassiveViewportScrollTop(input: {
  desiredScrollTop: number;
  next: {
    scrollTop: number;
    pendingDelta: number;
  };
  followDisabled: boolean;
  selectionLocked: boolean;
  sticky: boolean;
  maxScrollTop: number;
}): number | null {
  const { desiredScrollTop, next, followDisabled, selectionLocked, sticky, maxScrollTop } = input;
  const passiveViewportLocked = (followDisabled || selectionLocked) && !sticky;
  if (!passiveViewportLocked) {
    return null;
  }
  if (selectionLocked) {
    return null;
  }
  if (next.pendingDelta !== 0) {
    return null;
  }

  const normalizedDesiredScrollTop = Math.max(0, desiredScrollTop);
  if (normalizedDesiredScrollTop > maxScrollTop) {
    return null;
  }

  if (normalizedDesiredScrollTop === next.scrollTop) {
    return null;
  }

  return normalizedDesiredScrollTop;
}

export function TranscriptViewport({
  items,
  scrollRef,
  selectionLocked,
  followDisabled,
  onScrollHandleReady,
  onMetricsChange,
}: {
  items: TranscriptItem[];
  scrollRef: React.RefObject<ScrollBoxHandle | null>;
  selectionLocked?: boolean;
  followDisabled?: boolean;
  onScrollHandleReady?: () => void;
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
  const passiveScrollTopRef = useRef(scrollRef.current?.getScrollTop() ?? 0);
  const offsetsCacheRef = useRef<MeasuredOffsetsCache | null>(null);
  const setScrollBoxRef = useCallback(
    (handle: ScrollBoxHandle | null) => {
      scrollRef.current = handle;
      if (handle) {
        onScrollHandleReady?.();
      }
    },
    [onScrollHandleReady, scrollRef],
  );

  const itemKeys = useMemo(() => items.map((item) => item.id), [items]);
  const estimatedHeights = useMemo(() => {
    const next = new Map<string, number>();
    for (const item of items) {
      next.set(item.id, Math.max(1, item.estimatedHeight ?? 6));
    }
    return next;
  }, [items]);
  const offsetsCache = useMemo(() => {
    const nextCache = getMeasuredOffsetsCached({
      cache: offsetsCacheRef.current,
      version: measurementVersion,
      itemKeys,
      heightCache: heightCacheRef.current,
      estimatedHeight: 6,
      estimatedHeights,
    });
    offsetsCacheRef.current = nextCache;
    return nextCache;
  }, [estimatedHeights, itemKeys, measurementVersion]);

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
    const initialSnapshot = {
      scrollTop: handle.getScrollTop(),
      viewportHeight: handle.getViewportHeight(),
      pendingDelta: handle.getPendingDelta(),
    };
    passiveScrollTopRef.current = initialSnapshot.scrollTop;
    setScrollSnapshot(initialSnapshot);
    return handle.subscribe(() => {
      const nextSnapshot = {
        scrollTop: handle.getScrollTop(),
        viewportHeight: handle.getViewportHeight(),
        pendingDelta: handle.getPendingDelta(),
      };
      const diagnostics = handle.getPaintDiagnostics();
      const sticky = handle.isSticky();
      if (shouldUpdatePassiveScrollAnchor({
        pendingDelta: nextSnapshot.pendingDelta,
        mutationSource: diagnostics.mutationSource,
        followDisabled: Boolean(followDisabled),
        selectionLocked: Boolean(selectionLocked),
        sticky,
      })) {
        passiveScrollTopRef.current = nextSnapshot.scrollTop;
      }
      setScrollSnapshot(nextSnapshot);
    });
  }, [followDisabled, scrollRef, selectionLocked]);

  const range = useMemo(
    () =>
      computeMeasuredRange({
        itemKeys,
        heightCache: heightCacheRef.current,
        estimatedHeight: 6,
        estimatedHeights,
        scrollTop: scrollSnapshot.scrollTop,
        viewportHeight: scrollSnapshot.viewportHeight,
        overscan: 2,
        pendingDelta: scrollSnapshot.pendingDelta,
        offsets: offsetsCache.offsets,
      }),
    [estimatedHeights, itemKeys, offsetsCache.offsets, scrollSnapshot],
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
    const nextClampMin = range.startIndex < offsets.length ? offsets[range.startIndex] : undefined;
    const nextClampMax =
      range.endIndex > 0 && range.endIndex - 1 < offsets.length
        ? (offsets[range.endIndex - 1] ?? 0) +
          (heightCacheRef.current.get(items[range.endIndex - 1]?.id ?? "") ??
            items[range.endIndex - 1]?.estimatedHeight ??
            6)
        : undefined;
    const handle = scrollRef.current;
    const sticky = handle?.isSticky() ?? false;
    const shouldExposeClamp = shouldExposeMountedRangeClamp({
      pendingDelta: scrollSnapshot.pendingDelta,
      followDisabled: Boolean(followDisabled),
      selectionLocked: Boolean(selectionLocked),
      sticky,
    });
    const clampMin = shouldExposeClamp ? nextClampMin : undefined;
    const clampMax = shouldExposeClamp ? nextClampMax : undefined;
    handle?.setClampBounds(clampMin, clampMax);

    if (handle) {
      let nextSnapshot = {
        scrollTop: handle.getScrollTop(),
        viewportHeight: handle.getViewportHeight(),
        pendingDelta: handle.getPendingDelta(),
      };
      const maxScrollTop = Math.max(0, (handle.getScrollHeight() ?? 0) - (handle.getViewportHeight() ?? 0));
      const passiveViewportLocked = (Boolean(followDisabled) || Boolean(selectionLocked)) && !sticky;
      const preservedScrollTop = shouldPreservePassiveViewportScrollTop({
        desiredScrollTop: passiveScrollTopRef.current,
        next: nextSnapshot,
        followDisabled: Boolean(followDisabled),
        selectionLocked: Boolean(selectionLocked),
        sticky,
        maxScrollTop,
      });
      if (preservedScrollTop !== null) {
        const anchorIndex = Math.min(range.startIndex, Math.max(0, items.length - 1));
        const anchorItem = items[anchorIndex];
        const anchorEl = anchorItem ? itemRefs.current.get(anchorItem.id) : null;
        const anchorTop = anchorIndex < range.offsets.length ? (range.offsets[anchorIndex] ?? 0) : 0;
        const anchorOffset = preservedScrollTop - anchorTop;
        if (anchorEl) {
          handle.scrollToElement(anchorEl, anchorOffset);
        } else {
          handle.scrollTo(preservedScrollTop);
        }
        nextSnapshot = {
          scrollTop: preservedScrollTop,
          viewportHeight: handle.getViewportHeight(),
          pendingDelta: handle.getPendingDelta(),
        };
      }
      if (passiveViewportLocked && nextSnapshot.pendingDelta === 0) {
        passiveScrollTopRef.current = nextSnapshot.scrollTop;
      } else if (!passiveViewportLocked) {
        passiveScrollTopRef.current = nextSnapshot.scrollTop;
      }
      setScrollSnapshot((current) => (
        shouldRefreshViewportSnapshotAfterLayout({
          current,
          next: nextSnapshot,
          followDisabled: Boolean(followDisabled),
          selectionLocked: Boolean(selectionLocked),
          sticky,
        })
          ? nextSnapshot
          : current
      ));
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
  }, [
    columns,
    followDisabled,
    itemKeys,
    items,
    onMetricsChange,
    range.endIndex,
    range.startIndex,
    range.totalHeight,
    scrollRef,
    scrollSnapshot.pendingDelta,
    selectionLocked,
    visibleItems,
  ]);

  return (
    <ScrollBox
      ref={setScrollBoxRef}
      flexDirection="column"
      flexGrow={1}
      stickyScroll={!followDisabled && !selectionLocked}
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

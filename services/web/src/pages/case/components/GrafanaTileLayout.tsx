import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';

type GridColumns = 2 | 4 | 6 | 8;

const GRID_GAP_PX = 12;
const DEFAULT_CELL_SIZE_PX = 120;
const MAX_PANEL_SPAN = 8;

type PanelBlock = {
  type: 'panel';
  panelId: string;
  colSpan?: number;
  rowSpan?: number;
  title?: string;
};

type SectionBlock = {
  type: 'section';
  title: string;
  description?: string;
};

type BreakBlock = {
  type: 'break';
};

type SpacerBlock = {
  type: 'spacer';
  colSpan?: number;
  rowSpan?: number;
  showIfFirstInRow?: boolean;
};

type LayoutBlock = PanelBlock | SectionBlock | BreakBlock | SpacerBlock;

type GrafanaTileLayoutProps = {
  blocks: LayoutBlock[];
  grafanaProxyUrl?: string;
  grafanaBaseQuery: string | null;
};

type PreparedGridItem = {
  type: 'panel' | 'spacer';
  key: string;
  colSpan: number;
  rowSpan: number;
  showIfFirstInRow?: boolean;
  panelId?: string;
  title?: string;
};

type PlacedGridItem = PreparedGridItem & {
  colStart: number;
  rowStart: number;
};

type RenderSegment =
  | {
      type: 'section';
      key: string;
      block: SectionBlock;
    }
  | {
      type: 'grid';
      key: string;
      items: PlacedGridItem[];
      totalRows: number;
    };

const clamp = (value: number | undefined, min: number, max: number): number => {
  const candidate = Number.isFinite(value) ? Math.floor(value as number) : min;
  if (candidate < min) return min;
  if (candidate > max) return max;
  return candidate;
};

const getColumnCount = (viewportWidth: number): GridColumns => {
  if (viewportWidth >= 1280) return 8;
  if (viewportWidth >= 1024) return 6;
  if (viewportWidth >= 768) return 4;
  return 2;
};

const canFit = (
  occupied: Set<string>,
  rowStart: number,
  colStart: number,
  rowSpan: number,
  colSpan: number,
  columns: number,
): boolean => {
  if (colStart + colSpan - 1 > columns) return false;

  for (let row = rowStart; row < rowStart + rowSpan; row += 1) {
    for (let col = colStart; col < colStart + colSpan; col += 1) {
      if (occupied.has(`${row}:${col}`)) {
        return false;
      }
    }
  }

  return true;
};

const markOccupied = (
  occupied: Set<string>,
  rowStart: number,
  colStart: number,
  rowSpan: number,
  colSpan: number,
): void => {
  for (let row = rowStart; row < rowStart + rowSpan; row += 1) {
    for (let col = colStart; col < colStart + colSpan; col += 1) {
      occupied.add(`${row}:${col}`);
    }
  }
};

const packGridItems = (items: PreparedGridItem[], columns: GridColumns): { items: PlacedGridItem[]; totalRows: number } => {
  const occupied = new Set<string>();
  const placed: PlacedGridItem[] = [];
  let maxRow = 0;
  let bandStartRow: number | null = null;
  let bandEndRow = 0;
  let previousPlaced: PlacedGridItem | null = null;

  const findTopPlacementInBand = (
    item: PreparedGridItem,
  ): { rowStart: number; colStart: number } | null => {
    if (bandStartRow === null) return null;
    if (bandStartRow + item.rowSpan - 1 > bandEndRow) return null;

    for (let col = 1; col <= columns - item.colSpan + 1; col += 1) {
      if (!canFit(occupied, bandStartRow, col, item.rowSpan, item.colSpan, columns)) {
        continue;
      }
      if (item.type === 'spacer' && !item.showIfFirstInRow && col === 1) {
        continue;
      }
      return { rowStart: bandStartRow, colStart: col };
    }

    return null;
  };

  const findUnderPreviousInBand = (
    item: PreparedGridItem,
  ): { rowStart: number; colStart: number } | null => {
    if (!previousPlaced || bandStartRow === null) return null;

    const rowStart = previousPlaced.rowStart + previousPlaced.rowSpan;
    const colStart = previousPlaced.colStart;
    if (rowStart + item.rowSpan - 1 > bandEndRow) return null;
    if (colStart + item.colSpan - 1 > columns) return null;
    if (item.type === 'spacer' && !item.showIfFirstInRow && colStart === 1) return null;
    if (!canFit(occupied, rowStart, colStart, item.rowSpan, item.colSpan, columns)) return null;

    return { rowStart, colStart };
  };

  const findStartOfNewBand = (
    item: PreparedGridItem,
  ): { rowStart: number; colStart: number } | null => {
    const rowStart = maxRow + 1;

    for (let col = 1; col <= columns - item.colSpan + 1; col += 1) {
      if (!canFit(occupied, rowStart, col, item.rowSpan, item.colSpan, columns)) {
        continue;
      }
      if (item.type === 'spacer' && !item.showIfFirstInRow && col === 1) {
        continue;
      }
      return { rowStart, colStart: col };
    }

    return null;
  };

  for (const item of items) {
    let placement: { rowStart: number; colStart: number } | null = null;

    // Rule 1: try directly below previous tile, still inside current band.
    // Exception: if previous tile starts the row band (col 1), do not enforce stacking.
    if (!placement && bandStartRow !== null && previousPlaced && previousPlaced.colStart > 1) {
      placement = findUnderPreviousInBand(item);
    }

    // Rule 2: if not possible, align to top row in current band (anchored by first tile of band).
    if (!placement && bandStartRow !== null) {
      placement = findTopPlacementInBand(item);
    }

    // Rule 3: if neither works, start a new band; this tile becomes the band anchor.
    if (!placement) {
      placement = findStartOfNewBand(item);
      if (placement) {
        bandStartRow = placement.rowStart;
        bandEndRow = placement.rowStart + item.rowSpan - 1;
      }
    }

    if (!placement) {
      continue;
    }

    const placedItem: PlacedGridItem = {
      ...item,
      rowStart: placement.rowStart,
      colStart: placement.colStart,
    };

    markOccupied(occupied, placedItem.rowStart, placedItem.colStart, placedItem.rowSpan, placedItem.colSpan);
    maxRow = Math.max(maxRow, placedItem.rowStart + placedItem.rowSpan - 1);
    placed.push(placedItem);
    previousPlaced = placedItem;

    if (bandStartRow === null) {
      bandStartRow = placedItem.rowStart;
      bandEndRow = placedItem.rowStart + placedItem.rowSpan - 1;
    }
  }

  return { items: placed, totalRows: maxRow };
};

const buildSegments = (blocks: LayoutBlock[], columns: GridColumns): RenderSegment[] => {
  const segments: RenderSegment[] = [];
  let pendingGridItems: PreparedGridItem[] = [];
  let gridIndex = 0;
  let sectionIndex = 0;

  const flushGrid = () => {
    if (pendingGridItems.length === 0) return;

    const packed = packGridItems(pendingGridItems, columns);
    segments.push({
      type: 'grid',
      key: `grid-${gridIndex}`,
      items: packed.items,
      totalRows: packed.totalRows,
    });
    gridIndex += 1;
    pendingGridItems = [];
  };

  blocks.forEach((block, blockIndex) => {
    if (block.type === 'section') {
      flushGrid();
      segments.push({
        type: 'section',
        key: `section-${sectionIndex}`,
        block,
      });
      sectionIndex += 1;
      return;
    }

    if (block.type === 'break') {
      flushGrid();
      return;
    }

    if (block.type === 'panel') {
      pendingGridItems.push({
        type: 'panel',
        key: `panel-${blockIndex}-${block.panelId}`,
        panelId: block.panelId,
        title: block.title,
        colSpan: clamp(block.colSpan, 1, columns),
        rowSpan: clamp(block.rowSpan, 1, MAX_PANEL_SPAN),
      });
      return;
    }

    pendingGridItems.push({
      type: 'spacer',
      key: `spacer-${blockIndex}`,
      showIfFirstInRow: block.showIfFirstInRow,
      colSpan: clamp(block.colSpan, 1, columns),
      rowSpan: clamp(block.rowSpan, 1, MAX_PANEL_SPAN),
    });
  });

  flushGrid();
  return segments;
};

export type { LayoutBlock as GrafanaLayoutBlock };

export function GrafanaTileLayout({
  blocks,
  grafanaProxyUrl,
  grafanaBaseQuery,
}: GrafanaTileLayoutProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [columns, setColumns] = useState<GridColumns>(() =>
    typeof window === 'undefined' ? 8 : getColumnCount(window.innerWidth),
  );
  const [containerWidth, setContainerWidth] = useState(0);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const onResize = () => {
      setColumns(getColumnCount(window.innerWidth));
    };
    onResize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
    };
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    const element = containerRef.current;
    const observer = new ResizeObserver((entries) => {
      const [entry] = entries;
      if (!entry) return;
      setContainerWidth(entry.contentRect.width);
    });

    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  const cellSizePx = useMemo(() => {
    if (containerWidth <= 0) return DEFAULT_CELL_SIZE_PX;
    return (containerWidth - GRID_GAP_PX * (columns - 1)) / columns;
  }, [containerWidth, columns]);

  const segments = useMemo(() => buildSegments(blocks, columns), [blocks, columns]);

  const panelUrl = (panelId: string): string | null => {
    if (!grafanaProxyUrl || !grafanaBaseQuery) return null;
    const params = new URLSearchParams(grafanaBaseQuery);
    params.set('viewPanel', panelId);
    return `${grafanaProxyUrl}/embed?${params.toString()}`;
  };

  const toggleSection = (sectionKey: string) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [sectionKey]: !prev[sectionKey],
    }));
  };

  const renderedSegments: ReactNode[] = [];
  let currentSectionKey: string | null = null;

  segments.forEach((segment) => {
    if (segment.type === 'section') {
      currentSectionKey = segment.key;
      const isCollapsed = !!collapsedSections[segment.key];

      renderedSegments.push(
        <article
          key={segment.key}
          className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
        >
          <button
            type="button"
            className="flex w-full items-start justify-between gap-3 text-left"
            aria-expanded={!isCollapsed}
            onClick={() => toggleSection(segment.key)}
          >
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-slate-700">
                {segment.block.title}
              </h3>
              {segment.block.description ? (
                <p className="mt-1 text-sm text-slate-600">{segment.block.description}</p>
              ) : null}
            </div>
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600">
              <ChevronDown className={`h-4 w-4 transition-transform ${isCollapsed ? '-rotate-90' : 'rotate-0'}`} />
            </span>
          </button>
        </article>,
      );
      return;
    }

    const isHiddenBySection =
      currentSectionKey !== null && !!collapsedSections[currentSectionKey];

    renderedSegments.push(
      <div
        key={segment.key}
        className={`grid gap-3 ${isHiddenBySection ? 'hidden' : ''}`}
        style={{
          gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
          gridAutoRows: `${cellSizePx}px`,
          minHeight: segment.totalRows > 0 ? `${segment.totalRows * cellSizePx + (segment.totalRows - 1) * GRID_GAP_PX}px` : undefined,
        }}
      >
        {segment.items.map((item) => {
          const placementStyle = {
            gridColumn: `${item.colStart} / span ${item.colSpan}`,
            gridRow: `${item.rowStart} / span ${item.rowSpan}`,
          };

          if (item.type === 'spacer') {
            return <div key={item.key} aria-hidden style={placementStyle} />;
          }

          const src = panelUrl(item.panelId ?? '');
          const panelLabel = item.title || null;

          return (
            <div
              key={item.key}
              style={placementStyle}
              className="relative overflow-hidden rounded-xl border border-slate-200 bg-white"
            >
              {src ? (
                <>
                  <iframe
                    title={item.title || `Grafana panel ${item.panelId}`}
                    src={src}
                      className="h-full w-full"
                      allow="fullscreen"
                    />
                  {panelLabel ? (
                    <div className="pointer-events-none absolute left-2 top-2 rounded-md bg-white/90 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-slate-700">
                      {panelLabel}
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="flex h-full items-center bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900">
                  Missing Grafana proxy URL. Tile cannot be loaded.
                </div>
              )}
            </div>
          );
        })}
      </div>,
    );
  });

  return (
    <div ref={containerRef} className="space-y-3">
      {renderedSegments}
    </div>
  );
}

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useWindowVirtualizer } from '@tanstack/react-virtual'

import { TableBody, TableCell, TableRow } from '@/components/ui/table'

/** Lists shorter than this render normally: virtualising them would only cost accessibility and simplicity. */
export const VIRTUALIZE_FROM = 80

/** Distance from the top of the document, kept current as the layout above the list changes. */
function useDocumentOffset<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [offset, setOffset] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => setOffset(el.getBoundingClientRect().top + window.scrollY)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(document.body)
    return () => observer.disconnect()
  }, [])
  return { ref, offset }
}

/** Spread onto the row's `<tr>`: lets the virtualizer measure it and tells assistive technology its position. */
export interface VirtualRowProps {
  ref?: (el: Element | null) => void
  'data-index'?: number
  'aria-rowindex'?: number
}

interface VirtualTableBodyProps {
  count: number
  /** Estimated row height in px (rows are measured once rendered). */
  estimateSize: number
  /** Number of table columns, for the spacer rows. */
  columns: number
  renderRow: (index: number, rowProps: VirtualRowProps) => ReactNode
  /** Row keys; defaults to the index. */
  getKey?: (index: number) => string
}

/**
 * A `<tbody>` that renders only the rows near the viewport once a table is long (people tables at 1,000 employees),
 * keeping table semantics: spacer rows stand in for the rest, and rows carry `aria-rowindex` (the table should set
 * `aria-rowcount`), so assistive technology still learns the real size and position. The page itself scrolls, as
 * everywhere else in the app.
 */
export function VirtualTableBody({ count, estimateSize, columns, renderRow, getKey }: VirtualTableBodyProps) {
  const { ref, offset } = useDocumentOffset<HTMLTableSectionElement>()
  const enabled = count >= VIRTUALIZE_FROM
  // oxlint-disable-next-line react/incompatible-library -- the compiler then skips memoising this component, as intended
  const virtualizer = useWindowVirtualizer({
    count: enabled ? count : 0,
    estimateSize: () => estimateSize,
    overscan: 8,
    scrollMargin: offset,
    getItemKey: getKey ?? ((i) => i),
  })
  if (!enabled) {
    return <TableBody ref={ref}>{Array.from({ length: count }, (_, i) => renderRow(i, {}))}</TableBody>
  }
  const items = virtualizer.getVirtualItems()
  const before = items.length ? items[0].start - virtualizer.options.scrollMargin : 0
  const after = items.length ? virtualizer.getTotalSize() - (items[items.length - 1].end - virtualizer.options.scrollMargin) : 0
  return (
    <TableBody ref={ref}>
      {before > 0 && (
        <TableRow aria-hidden className="hover:bg-transparent">
          <TableCell colSpan={columns} style={{ height: before, padding: 0 }} />
        </TableRow>
      )}
      {items.map((item) =>
        renderRow(item.index, { ref: virtualizer.measureElement, 'data-index': item.index, 'aria-rowindex': item.index + 2 }),
      )}
      {after > 0 && (
        <TableRow aria-hidden className="hover:bg-transparent">
          <TableCell colSpan={columns} style={{ height: after, padding: 0 }} />
        </TableRow>
      )}
    </TableBody>
  )
}

interface VirtualGridProps<T> {
  items: T[]
  /** Accessible name of the list. */
  label: string
  /** Card height estimate in px. */
  estimateRowHeight: number
  /** Gap between rows in px (match the grid's CSS gap). */
  gap: number
  /** Columns at a given viewport width (match the grid's responsive classes). */
  columnsFor: (viewportWidth: number) => number
  /** Grid classes (columns and gap). */
  className: string
  itemClassName?: string
  renderItem: (item: T) => ReactNode
  getKey: (item: T) => string
}

/**
 * A responsive card grid (a list) that renders only the rows of cards near the viewport once it is long. Cards that
 * are scrolled away are unmounted, which also stops their timers and subscriptions. In virtual mode each card is
 * positioned individually, so the list stays a real `<ul>` of `<li>`s.
 */
export function VirtualGrid<T>({ items, label, estimateRowHeight, gap, columnsFor, className, itemClassName, renderItem, getKey }: VirtualGridProps<T>) {
  const { ref, offset } = useDocumentOffset<HTMLUListElement>()
  const [viewport, setViewport] = useState(() => window.innerWidth)
  useLayoutEffect(() => {
    const onResize = () => setViewport(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const columns = Math.max(1, columnsFor(viewport))
  const rowCount = Math.ceil(items.length / columns)
  const enabled = items.length >= VIRTUALIZE_FROM
  // oxlint-disable-next-line react/incompatible-library -- the compiler then skips memoising this component, as intended
  const virtualizer = useWindowVirtualizer({
    count: enabled ? rowCount : 0,
    estimateSize: () => estimateRowHeight + gap,
    overscan: 3,
    scrollMargin: offset,
  })
  if (!enabled) {
    return (
      <ul ref={ref} aria-label={label} className={className}>
        {items.map((value) => (
          <li key={getKey(value)} className={itemClassName}>
            {renderItem(value)}
          </li>
        ))}
      </ul>
    )
  }
  const width = `calc((100% - ${(columns - 1) * gap}px) / ${columns})`
  return (
    <ul ref={ref} aria-label={label} style={{ position: 'relative', height: virtualizer.getTotalSize() }}>
      {virtualizer.getVirtualItems().flatMap((row) =>
        items.slice(row.index * columns, row.index * columns + columns).map((value, column) => (
          <li
            key={getKey(value)}
            // The first card of each row is measured; the row's height follows it.
            ref={column === 0 ? virtualizer.measureElement : undefined}
            data-index={row.index}
            className={itemClassName}
            style={{
              position: 'absolute',
              top: 0,
              left: `calc(${column} * (${width} + ${gap}px))`,
              width,
              paddingBottom: gap,
              transform: `translateY(${row.start - virtualizer.options.scrollMargin}px)`,
            }}
          >
            {renderItem(value)}
          </li>
        )),
      )}
    </ul>
  )
}

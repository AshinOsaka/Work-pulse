import { useState } from 'react'
import { ArrowUpRight, CalendarRange, Database } from 'lucide-react'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ChartTooltipBox, ViewToggle, type ViewMode } from '@/features/dashboard/components/widget'
import type { CardCell, ChartCard, DataCard, ListCard, MetricsCard } from '@/features/assistant/api'
import { isInternal } from '@/features/assistant/markdown'
import { cn } from '@/lib/utils'

const ROWS_SHOWN = 8
const AXIS_TICK = { fill: 'var(--muted-foreground)', fontSize: 11 }

const show = (value: CardCell | undefined) => (value === null || value === undefined || value === '' ? '—' : String(value))

function CardLinkButton({ href, label }: { href: string; label: string }) {
  if (!isInternal(href)) return null
  return (
    <Link
      to={href}
      className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] font-medium text-primary transition hover:bg-primary-soft focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
    >
      {label}
      <ArrowUpRight className="size-3.5" aria-hidden />
    </Link>
  )
}

function DataTable({ columns, rows }: { columns: { key: string; label: string }[]; rows: (Record<string, CardCell> & { href?: string | null })[] }) {
  const [all, setAll] = useState(false)
  const visible = all ? rows : rows.slice(0, ROWS_SHOWN)
  return (
    <div>
      <div className="relative overflow-x-auto rounded-md border">
        <Table className="text-[13px]">
          <TableHeader>
            <TableRow>
              {columns.map((c) => (
                <TableHead key={c.key} className="h-8 whitespace-nowrap">
                  {c.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((row, r) => (
              <TableRow key={r}>
                {columns.map((c, n) => (
                  <TableCell key={c.key} className={cn('py-1.5 tabular', show(row[c.key]).length <= 16 && 'whitespace-nowrap')}>
                    {n === 0 && row.href && isInternal(row.href) ? (
                      <Link to={row.href} className="font-medium text-primary underline-offset-2 hover:underline">
                        {show(row[c.key])}
                      </Link>
                    ) : (
                      show(row[c.key])
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {rows.length > ROWS_SHOWN && (
        <button type="button" onClick={() => setAll(!all)} className="mt-1.5 text-[12px] font-medium text-primary hover:underline">
          {all ? 'Show fewer' : `Show all ${rows.length} rows`}
        </button>
      )}
    </div>
  )
}

function Metrics({ card }: { card: MetricsCard }) {
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {card.metrics.map((m) => (
          <div key={m.label} className="rounded-md bg-muted/50 px-3 py-2">
            <dt className="text-[11px] font-medium text-muted-foreground">{m.label}</dt>
            <dd className="mt-0.5 text-lg font-semibold tracking-tight tabular">{m.value}</dd>
            {m.hint && <dd className="text-[11px] text-muted-foreground">{m.hint}</dd>}
          </div>
        ))}
      </dl>
      {card.columns && card.columns.length > 0 && card.rows && card.rows.length > 0 && <DataTable columns={card.columns} rows={card.rows} />}
    </div>
  )
}

function BarTooltip({ active, payload, title, format }: { active?: boolean; payload?: { payload?: { label: string; value: number } }[]; title: string; format: (v: number) => string }) {
  const point = payload?.[0]?.payload
  return active && point ? <ChartTooltipBox title={point.label} rows={[{ label: title, value: format(point.value) }]} /> : null
}

function Chart({ card }: { card: ChartCard }) {
  const [view, setView] = useState<ViewMode>('chart')
  const format = (v: number) => `${v}${card.unit === 'h' ? 'h' : card.unit ? ` ${card.unit}` : ''}`
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <ViewToggle value={view} onChange={setView} />
      </div>
      {view === 'chart' ? (
        <figure className="h-44">
          <figcaption className="sr-only">{`${card.title}, ${card.period}. Switch to the table view for every value.`}</figcaption>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={card.series} margin={{ top: 6, right: 4, bottom: 0, left: 0 }} barCategoryGap={4}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={12} tick={AXIS_TICK} />
              <YAxis tickFormatter={format} tickLine={false} axisLine={false} width={40} tick={AXIS_TICK} allowDecimals={false} />
              <Tooltip cursor={{ fill: 'var(--accent)', opacity: 0.6 }} content={<BarTooltip title={card.title} format={format} />} />
              <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </figure>
      ) : (
        <DataTable
          columns={[
            { key: 'label', label: 'Day' },
            { key: 'value', label: card.unit === 'h' ? 'Hours' : 'Value' },
          ]}
          rows={card.series.map((s) => ({ label: s.label, value: format(s.value) }))}
        />
      )}
    </div>
  )
}

function Items({ card }: { card: ListCard }) {
  return (
    <ul className="divide-y rounded-md border">
      {card.items.map((item, n) => (
        <li key={n} className="flex items-center justify-between gap-3 px-3 py-2 text-[13px]">
          <div className="min-w-0">
            {item.href && isInternal(item.href) ? (
              <Link to={item.href} className="font-medium text-foreground hover:text-primary hover:underline">
                {item.title}
              </Link>
            ) : (
              <p className="font-medium">{item.title}</p>
            )}
            {item.meta && <p className="text-[12px] text-muted-foreground">{item.meta}</p>}
          </div>
        </li>
      ))}
    </ul>
  )
}

export function AnswerCard({ card }: { card: DataCard }) {
  return (
    <section aria-label={card.title} className="rounded-lg border bg-card p-3.5 shadow-xs">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold">{card.title}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <CalendarRange className="size-3" aria-hidden />
              <span className="sr-only">Period: </span>
              {card.period}
            </span>
            <span className="inline-flex items-center gap-1">
              <Database className="size-3" aria-hidden />
              <span className="sr-only">Source: </span>
              {card.source}
            </span>
          </p>
        </div>
        {card.link && <CardLinkButton href={card.link.href} label={card.link.label} />}
      </header>
      {card.kind === 'metrics' && <Metrics card={card} />}
      {card.kind === 'table' && (card.rows.length ? <DataTable columns={card.columns} rows={card.rows} /> : <p className="text-[13px] text-muted-foreground">No rows.</p>)}
      {card.kind === 'chart' && <Chart card={card} />}
      {card.kind === 'list' && <Items card={card} />}
      {card.note && <p className="mt-2 text-[11px] text-muted-foreground">{card.note}</p>}
    </section>
  )
}

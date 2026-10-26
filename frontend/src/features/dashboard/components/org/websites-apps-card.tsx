import { useState } from 'react'
import { Link } from 'react-router'
import { AppWindow, Globe } from 'lucide-react'

import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { WidgetCard, WidgetError, WidgetUnavailable } from '@/features/dashboard/components/widget'
import { formatShort } from '@/features/dashboard/components/org/shared'
import type { ApplicationUsageReport, WebsiteUsageReport } from '@/types/api'

interface Props {
  websites: WebsiteUsageReport | undefined
  applications: ApplicationUsageReport | undefined
  isPending: boolean
  isError: boolean
  error: unknown
  isRefreshing: boolean
  onRetry: () => void
}

type Tab = 'websites' | 'applications'

interface Item {
  key: string
  name: string
  seconds: number
}

function UsageList({ items }: { items: Item[] }) {
  const max = Math.max(1, ...items.map((i) => i.seconds))
  return (
    <ul className="divide-y">
      {items.slice(0, 6).map((item) => (
        <li key={item.key} className="flex items-center gap-3 px-5 py-2.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-[11px] font-semibold uppercase text-muted-foreground">
            {item.name.replace(/^www\./, '').charAt(0)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium">{item.name}</p>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round((100 * item.seconds) / max)}%` }} />
            </div>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-[13px] font-semibold tabular">{formatShort(item.seconds)}</p>
            <p className="text-[11px] text-muted-foreground">time spent</p>
          </div>
        </li>
      ))}
    </ul>
  )
}

export function WebsitesApplicationsCard({ websites, applications, isPending, isError, error, isRefreshing, onRetry }: Props) {
  const [tab, setTab] = useState<Tab>('websites')
  const siteItems: Item[] = (websites?.websites ?? []).map((w) => ({ key: w.domain, name: w.domain, seconds: w.seconds }))
  const appItems: Item[] = (applications?.applications ?? []).map((a) => ({ key: a.app_id, name: a.app_name, seconds: a.seconds }))

  return (
    <WidgetCard
      title={
        <span className="inline-flex items-center gap-2">
          <Globe className="size-4 text-primary" aria-hidden /> Websites &amp; Applications
        </span>
      }
      description="Most used websites and applications"
      refreshing={isRefreshing}
      actions={
        <SegmentedControl<Tab>
          size="sm"
          label="Show"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'websites', label: 'Websites' },
            { value: 'applications', label: 'Applications' },
          ]}
        />
      }
    >
      {isError ? (
        <WidgetError error={error} onRetry={onRetry} />
      ) : isPending ? (
        <div className="space-y-3 p-5">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : tab === 'websites' ? (
        websites && !websites.tracking_enabled ? (
          <WidgetUnavailable
            icon={Globe}
            title="Website tracking is off"
            description="Turn on website tracking in Settings → Monitoring & privacy to see which sites are used."
          />
        ) : siteItems.length ? (
          <UsageList items={siteItems} />
        ) : (
          <WidgetUnavailable icon={Globe} title="No website activity in this range" description="Domains appear once employees browse supported browsers while tracked." />
        )
      ) : appItems.length ? (
        <UsageList items={appItems} />
      ) : (
        <WidgetUnavailable icon={AppWindow} title="No application activity in this range" description="Application time appears once the desktop agent records foreground use." />
      )}
      <div className="border-t px-5 py-2.5">
        <Link to="/activity" className="text-[12px] font-medium text-primary hover:underline">
          Open the full report →
        </Link>
      </div>
    </WidgetCard>
  )
}

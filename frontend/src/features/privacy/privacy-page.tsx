import { useQuery } from '@tanstack/react-query'
import {
  AppWindow,
  Ban,
  Camera,
  Clock,
  FileChartColumn,
  FolderKanban,
  Mail,
  MonitorPlay,
  ScrollText,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'

import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { WidgetError } from '@/features/dashboard/components/widget'
import { api } from '@/lib/api-client'
import { formatDateTime } from '@/lib/format'

type Status = 'on' | 'off' | 'on_request'

interface PolicySection {
  key: string
  title: string
  status: Status
  summary: string
  what: string[]
  when: string
  why: string
  retention: string
  access: { role: string; scope: string }[]
  safeguards: string[]
}

interface MonitoringPolicy {
  workspace: string
  timezone: string
  last_changed_at: string | null
  personal_screenshot_setting: boolean
  sections: PolicySection[]
  never_collected: string[]
  contacts: { name: string; email: string }[]
}

const ICONS: Record<string, LucideIcon> = {
  presence: Clock,
  activity: AppWindow,
  screenshots: Camera,
  live: MonitorPlay,
  work: FolderKanban,
  audit: ScrollText,
  derived: FileChartColumn,
}

const STATUS: Record<Status, { label: string; variant: 'success' | 'secondary' | 'info' }> = {
  on: { label: 'Collected', variant: 'success' },
  off: { label: 'Off', variant: 'secondary' },
  on_request: { label: 'Only on request', variant: 'info' },
}

export const useMonitoringPolicy = () =>
  useQuery({ queryKey: ['privacy', 'monitoring-policy'], queryFn: () => api.get<MonitoringPolicy>('/privacy/monitoring-policy'), staleTime: 60_000 })

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-2 sm:grid-cols-[8.5rem_1fr] sm:gap-4">
      <dt className="text-[12px] font-medium text-muted-foreground">{label}</dt>
      <dd className="text-[13px]">{children}</dd>
    </div>
  )
}

function Section({ section, personal }: { section: PolicySection; personal: boolean }) {
  const Icon = ICONS[section.key] ?? ShieldCheck
  const status = STATUS[section.status]
  const off = section.status === 'off'
  return (
    <Card className="gap-0 p-5" aria-labelledby={`policy-${section.key}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground" aria-hidden>
            <Icon className="size-4" />
          </div>
          <div className="min-w-0">
            <h2 id={`policy-${section.key}`} className="text-[15px] font-semibold">
              {section.title}
            </h2>
            <p className="text-[13px] text-muted-foreground">
              {section.summary}
              {section.key === 'screenshots' && personal && ' (a setting for you personally)'}
            </p>
          </div>
        </div>
        <Badge variant={status.variant} className="shrink-0">
          {status.label}
        </Badge>
      </div>
      {!off && (
        <dl className="mt-3 divide-y border-t">
          <Row label="What">
            <ul className="list-disc space-y-0.5 pl-4 marker:text-muted-foreground">
              {section.what.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </Row>
          <Row label="When">{section.when}</Row>
          <Row label="Why">{section.why}</Row>
          <Row label="Kept for">{section.retention}</Row>
          <Row label="Who can see it">
            <ul className="space-y-0.5">
              {section.access.map((a) => (
                <li key={a.role}>
                  <span className="font-medium">{a.role}</span> <span className="text-muted-foreground">· {a.scope}</span>
                </li>
              ))}
            </ul>
          </Row>
          {section.safeguards.length > 0 && (
            <Row label="Safeguards">
              <ul className="space-y-0.5">
                {section.safeguards.map((s) => (
                  <li key={s} className="flex gap-1.5">
                    <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden />
                    {s}
                  </li>
                ))}
              </ul>
            </Row>
          )}
        </dl>
      )}
    </Card>
  )
}

export default function PrivacyPage() {
  const policy = useMonitoringPolicy()
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Monitoring & privacy"
        icon={ShieldCheck}
        description={
          policy.data
            ? `What ${policy.data.workspace} records about your work, when, why, for how long and who can see it. This page always reflects the current settings.`
            : 'What is recorded about your work, when, why, for how long and who can see it.'
        }
      />
      {policy.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : policy.isError ? (
        <WidgetError error={policy.error} onRetry={() => void policy.refetch()} />
      ) : (
        <>
          <Card className="gap-3 border-success/30 bg-success-soft/40 p-5">
            <h2 className="flex items-center gap-2 text-[15px] font-semibold">
              <Ban className="size-4 text-success" aria-hidden /> Never collected
            </h2>
            <ul className="grid gap-1.5 text-[13px] sm:grid-cols-2">
              {policy.data.never_collected.map((item) => (
                <li key={item} className="flex gap-2">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          </Card>
          {policy.data.sections.map((section) => (
            <Section key={section.key} section={section} personal={policy.data.personal_screenshot_setting} />
          ))}
          <Card className="gap-2 p-5 text-[13px]">
            <h2 className="text-[15px] font-semibold">Questions or concerns</h2>
            <p className="text-muted-foreground">
              Ask your administrator{policy.data.contacts.length > 1 ? 's' : ''}. Times are shown in {policy.data.timezone}.
              {policy.data.last_changed_at && ` Monitoring settings last changed ${formatDateTime(policy.data.last_changed_at)}.`}
            </p>
            <ul className="flex flex-wrap gap-x-5 gap-y-1">
              {policy.data.contacts.map((c) => (
                <li key={c.email}>
                  <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline">
                    <Mail className="size-3.5" aria-hidden />
                    {c.name}
                  </a>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  )
}

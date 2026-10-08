import { CircleDashed, Link2 } from 'lucide-react'

import { PageHeader } from '@/components/common/page-header'
import { ComingSoonBadge } from '@/components/common/status'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getModule } from '@/config/modules'
import { RequirePermission } from '@/features/auth/guards'

/** Decorative wireframe of the future module layout — no data, clearly labelled. */
function LayoutPreview() {
  return (
    <div className="relative overflow-hidden rounded-xl border bg-subtle p-4" aria-hidden>
      <div className="mb-4 flex gap-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex-1 space-y-2 rounded-lg border bg-card p-3">
            <div className="h-2 w-1/2 rounded bg-muted" />
            <div className="h-4 w-1/3 rounded bg-muted" />
          </div>
        ))}
      </div>
      <div className="space-y-2 rounded-lg border bg-card p-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 py-1">
            <div className="size-6 rounded-full bg-muted" />
            <div className="h-2 flex-1 rounded bg-muted" style={{ maxWidth: `${70 - i * 12}%` }} />
            <div className="h-2 w-12 rounded bg-muted" />
          </div>
        ))}
      </div>
      <div className="absolute inset-0 bg-gradient-to-t from-subtle via-subtle/30 to-transparent" />
      <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border bg-card px-2.5 py-1 text-[11px] font-medium text-muted-foreground shadow-xs">
        Layout preview · no data
      </span>
    </div>
  )
}

export default function ComingSoonPage({ moduleKey }: { moduleKey: string }) {
  const module = getModule(moduleKey)

  return (
    <RequirePermission permission={module.permission}>
      <div className="space-y-6">
        <PageHeader
          title={module.label}
          description={module.description}
          icon={module.icon}
          badge={<ComingSoonBadge long />}
        />

        <Card className="overflow-hidden">
          <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="flex flex-col p-6 sm:p-8">
              <p className="text-[12px] font-medium tracking-wide text-primary uppercase">
                On the roadmap
              </p>
              <h2 className="mt-2 text-lg font-semibold tracking-tight">This module isn't available yet</h2>
              <p className="mt-1.5 text-[13px] text-muted-foreground">
                {module.label} is on the WorkPulse roadmap and will arrive in a future release. Here is what it is
                planned to include.
              </p>

              {module.planned && (
                <div className="mt-6">
                  <p className="text-[12px] font-medium text-muted-foreground">Planned capabilities</p>
                  <ul className="mt-2.5 space-y-2.5">
                    {module.planned.map((item) => (
                      <li key={item} className="flex items-start gap-2.5 text-[13px]">
                        <CircleDashed className="mt-0.5 size-4 shrink-0 text-primary/70" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {module.dependsOn && (
                <p className="mt-6 flex items-center gap-2 border-t pt-4 text-[12px] text-muted-foreground">
                  <Link2 className="size-3.5" /> Depends on: {module.dependsOn}
                </p>
              )}
            </div>
            <div className="border-t bg-subtle/50 p-6 lg:border-t-0 lg:border-l">
              <LayoutPreview />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader className="pb-5">
            <CardTitle>Access</CardTitle>
            <CardDescription>
              {module.permission ? (
                <>
                  Visible to roles with the <code className="rounded bg-muted px-1 py-0.5 text-[12px]">{module.permission}</code>{' '}
                  permission. Access rules are already enforced.
                </>
              ) : (
                'Every member of the workspace will be able to use this module for their own data.'
              )}
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    </RequirePermission>
  )
}

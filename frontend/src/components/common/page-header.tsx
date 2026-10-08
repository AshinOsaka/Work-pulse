import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks/use-document-title'

interface PageHeaderProps {
  title: string
  description?: ReactNode
  icon?: LucideIcon
  badge?: ReactNode
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, description, icon: Icon, badge, actions, className }: PageHeaderProps) {
  useDocumentTitle(title)
  return (
    <div className={cn('flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="flex min-w-0 items-start gap-3.5">
        {Icon && (
          <div className="mt-0.5 hidden size-10 shrink-0 items-center justify-center rounded-lg border bg-card text-primary shadow-xs sm:flex">
            <Icon className="size-5" />
          </div>
        )}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-balance sm:text-[22px]">{title}</h1>
            {badge}
          </div>
          {description && <p className="mt-1 text-[13px] text-muted-foreground sm:text-sm">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
  size?: 'sm' | 'md'
}

export function EmptyState({ icon: Icon, title, description, action, className, size = 'md' }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        size === 'md' ? 'gap-3 px-6 py-12' : 'gap-2 px-4 py-8',
        className,
      )}
    >
      <div className="relative">
        <div className="absolute inset-0 scale-150 rounded-full bg-primary/10 blur-xl" aria-hidden />
        <div
          className={cn(
            'relative flex items-center justify-center rounded-xl border bg-card text-muted-foreground shadow-xs',
            size === 'md' ? 'size-11' : 'size-9',
          )}
        >
          <Icon className={size === 'md' ? 'size-5' : 'size-4'} />
        </div>
      </div>
      <div className="max-w-sm space-y-1">
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="text-[13px] text-pretty text-muted-foreground">{description}</p>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}

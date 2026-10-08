import type { LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router'

import { cn } from '@/lib/utils'

export interface LinkTab {
  to: string
  label: string
  icon?: LucideIcon
  /** Match only the exact path (for index tabs). */
  end?: boolean
}

/** Route-driven tabs that look like `Tabs`, so sub-pages get real, shareable URLs. */
export function LinkTabs({ tabs, className }: { tabs: LinkTab[]; className?: string }) {
  return (
    <nav className={cn('flex w-full items-center gap-5 overflow-x-auto border-b text-muted-foreground', className)}>
      {tabs.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              '-mb-px inline-flex items-center gap-1.5 border-b-2 border-transparent pt-1 pb-2.5 text-[13px] font-medium whitespace-nowrap transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none',
              isActive && 'border-primary text-foreground',
            )
          }
        >
          {Icon && <Icon className="size-4" />}
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

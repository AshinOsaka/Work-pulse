import { useState } from 'react'
import { ChevronDown, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { NavLink, useLocation } from 'react-router'

import { Logo } from '@/components/common/logo'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { MODULES, NAV_SECTIONS, type AppModule } from '@/config/modules'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'
import { useUiStore } from '@/stores/ui-store'

export function useVisibleModules(): AppModule[] {
  const { can } = usePermissions()
  const allowed = (m: AppModule) => !m.permission || can(m.permission)
  return MODULES.flatMap((m) => {
    if (!m.children) return allowed(m) ? [m] : []
    const children = m.children.filter(allowed)
    // A parent (e.g. Live Tracking) shows only when at least one of its sub-items is visible.
    return children.length && allowed(m) ? [{ ...m, children }] : []
  })
}

function NavItem({ module, collapsed, onNavigate }: { module: AppModule; collapsed: boolean; onNavigate?: () => void }) {
  const Icon = module.icon
  const link = (
    <NavLink
      to={module.path}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors',
          'text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground',
          isActive && 'bg-sidebar-active text-sidebar-active-foreground hover:bg-sidebar-active hover:text-sidebar-active-foreground',
          collapsed && 'justify-center px-0',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && !collapsed && (
            <span className="absolute top-1.5 bottom-1.5 -left-3 w-[3px] rounded-r-full bg-primary" aria-hidden />
          )}
          <Icon className={cn('size-4 shrink-0', isActive ? 'text-primary' : 'opacity-80 group-hover:opacity-100')} />
          {!collapsed && (
            <>
              <span className="truncate">{module.label}</span>
              {module.status === 'upcoming' && (
                <span className="ml-auto rounded px-1 text-[10px] font-medium text-muted-foreground ring-1 ring-border">
                  Soon
                </span>
              )}
            </>
          )}
        </>
      )}
    </NavLink>
  )

  if (!collapsed) return link
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">
        {module.label}
        {module.status === 'upcoming' && <span className="ml-1.5 opacity-70">· Soon</span>}
      </TooltipContent>
    </Tooltip>
  )
}

/** A sub-item under an expandable parent, shown with a bullet dot (e.g. Screenshot, Live Stream). */
function SubNavItem({ module, onNavigate }: { module: AppModule; onNavigate?: () => void }) {
  return (
    <NavLink
      to={module.path}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex h-8 items-center gap-2.5 rounded-md pr-2.5 pl-9 text-[13px] font-medium transition-colors',
          'text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground',
          isActive && 'bg-sidebar-active text-sidebar-active-foreground hover:bg-sidebar-active hover:text-sidebar-active-foreground',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute top-1.5 bottom-1.5 left-[14px] w-[3px] rounded-r-full bg-primary" aria-hidden />}
          <span className={cn('size-1.5 shrink-0 rounded-full', isActive ? 'bg-primary' : 'bg-muted-foreground/50 group-hover:bg-muted-foreground')} aria-hidden />
          <span className="truncate">{module.label}</span>
          {module.status === 'upcoming' && (
            <span className="ml-auto rounded px-1 text-[10px] font-medium text-muted-foreground ring-1 ring-border">Soon</span>
          )}
        </>
      )}
    </NavLink>
  )
}

/** An expandable parent (e.g. Live Tracking) with nested sub-items. */
function NavGroup({ module, collapsed, onNavigate }: { module: AppModule; collapsed: boolean; onNavigate?: () => void }) {
  const { pathname } = useLocation()
  const children = module.children ?? []
  const hasActiveChild = children.some((c) => pathname === c.path || pathname.startsWith(`${c.path}/`))
  const [open, setOpen] = useState(hasActiveChild)
  const expanded = open || hasActiveChild

  // No room to nest in the icon rail: show each sub-item as its own icon.
  if (collapsed) {
    return (
      <>
        {children.map((child) => (
          <NavItem key={child.key} module={child} collapsed onNavigate={onNavigate} />
        ))}
      </>
    )
  }

  const Icon = module.icon
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={expanded}
        className={cn(
          'group flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors',
          'text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground',
          hasActiveChild && 'text-foreground',
        )}
      >
        <Icon className={cn('size-4 shrink-0', hasActiveChild ? 'text-primary' : 'opacity-80 group-hover:opacity-100')} />
        <span className="truncate">{module.label}</span>
        <ChevronDown className={cn('ml-auto size-3.5 text-muted-foreground transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <div className="mt-0.5 space-y-0.5">
          {children.map((child) => (
            <SubNavItem key={child.key} module={child} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </div>
  )
}

export function SidebarContent({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const modules = useVisibleModules()

  return (
    <div className="flex h-full flex-col">
      <div className={cn('flex h-14 shrink-0 items-center border-b border-sidebar-border', collapsed ? 'justify-center px-2' : 'px-4')}>
        <Logo collapsed={collapsed} />
      </div>

      <nav className={cn('flex-1 space-y-5 overflow-y-auto pt-4 pb-4', collapsed ? 'px-2' : 'px-3')} aria-label="Main">
        {NAV_SECTIONS.map((section) => {
          const items = modules.filter((m) => m.section === section)
          if (!items.length) return null
          return (
            <div key={section} className="space-y-0.5">
              {collapsed ? (
                <div className="mx-auto mb-2 h-px w-6 bg-sidebar-border first:hidden" aria-hidden />
              ) : (
                <p className="px-2.5 pb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  {section}
                </p>
              )}
              {items.map((module) =>
                module.children?.length ? (
                  <NavGroup key={module.key} module={module} collapsed={collapsed} onNavigate={onNavigate} />
                ) : (
                  <NavItem key={module.key} module={module} collapsed={collapsed} onNavigate={onNavigate} />
                ),
              )}
            </div>
          )
        })}
      </nav>
    </div>
  )
}

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed)
  const toggle = useUiStore((s) => s.toggleSidebar)

  return (
    <aside
      className={cn(
        'group/sidebar fixed inset-y-0 left-0 z-30 hidden border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-out lg:block',
        collapsed ? 'w-16' : 'w-64',
      )}
    >
      <SidebarContent collapsed={collapsed} />
      <button
        type="button"
        onClick={toggle}
        className="absolute top-[18px] -right-3 z-10 flex size-6 items-center justify-center rounded-full border bg-card text-muted-foreground opacity-0 shadow-xs transition group-hover/sidebar:opacity-100 hover:text-foreground focus-visible:opacity-100"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronsRight className="size-3.5" /> : <ChevronsLeft className="size-3.5" />}
      </button>
    </aside>
  )
}

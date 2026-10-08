import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { NavLink } from 'react-router'

import { Logo } from '@/components/common/logo'
import { StatusDot, type StatusTone } from '@/components/common/status'
import { Progress } from '@/components/ui/misc'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { MODULES, NAV_SECTIONS, type AppModule } from '@/config/modules'
import { useOnline } from '@/hooks/use-online'
import { useHealth } from '@/hooks/use-system'
import { capitalize, daysUntil } from '@/lib/format'
import { useRealtimeStore, type RealtimeStatus } from '@/lib/realtime'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import { useUiStore } from '@/stores/ui-store'

export function useVisibleModules(): AppModule[] {
  const { can } = usePermissions()
  return MODULES.filter((m) => !m.permission || can(m.permission))
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

const realtimeTone: Record<RealtimeStatus, StatusTone> = {
  idle: 'neutral',
  connecting: 'warning',
  connected: 'success',
  disconnected: 'danger',
}

function SystemStatus({ collapsed }: { collapsed: boolean }) {
  const health = useHealth()
  const online = useOnline()
  const realtime = useRealtimeStore((s) => s.status)
  // A failed check outranks the last good answer, and being offline outranks both.
  const apiState = !online ? 'offline' : health.isPending ? 'checking' : health.isError ? 'unreachable' : health.data?.status === 'ok' ? 'ok' : 'degraded'
  const apiTone: StatusTone = { offline: 'danger', checking: 'neutral', unreachable: 'danger', ok: 'success', degraded: 'warning' }[apiState] as StatusTone
  const apiLabel = { offline: 'Offline', checking: 'Checking…', unreachable: 'Unreachable', ok: 'Operational', degraded: 'Degraded' }[apiState]
  const realtimeLabel = online
    ? { idle: 'Idle', connecting: 'Connecting…', connected: 'Connected', disconnected: 'Reconnecting…' }[realtime]
    : 'Offline'
  const realtimeDot: StatusTone = online ? realtimeTone[realtime] : 'danger'

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className="flex h-8 w-full items-center justify-center rounded-md" aria-label={`API ${apiLabel}`}>
            <StatusDot tone={apiTone} pulse={apiTone === 'success'} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right">
          API: {apiLabel} · Realtime: {realtimeLabel}
        </TooltipContent>
      </Tooltip>
    )
  }

  const healthy = apiState === 'ok' && realtime === 'connected'
  if (healthy) {
    // One quiet line while everything works; the details are a hover away.
    return (
      <div
        data-slot="system-status"
        className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-[12px] font-medium shadow-xs"
        title={`API: ${apiLabel} · Realtime: ${realtimeLabel}`}
      >
        <StatusDot tone="success" pulse /> All systems operational
      </div>
    )
  }

  return (
    <div data-slot="system-status" className="space-y-1.5 rounded-lg border bg-card px-3 py-2.5 text-[12px] shadow-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground">API</span>
        <span className="flex items-center gap-1.5 font-medium">
          <StatusDot tone={apiTone} pulse={apiTone === 'success'} /> {apiLabel}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground">Realtime</span>
        <span className="flex items-center gap-1.5 font-medium">
          <StatusDot tone={realtimeDot} /> {realtimeLabel}
        </span>
      </div>
    </div>
  )
}

function TrialCard() {
  const company = useAuthStore((s) => s.company)
  const remaining = daysUntil(company?.trial_ends_at)
  if (company?.plan !== 'trial' || remaining === null || !company.trial_ends_at) return null
  const total = Math.max(1, Math.round((Date.parse(company.trial_ends_at) - Date.parse(company.created_at)) / 86_400_000))
  return (
    <div className="rounded-lg border bg-gradient-to-br from-primary-soft/80 to-card px-3 py-2.5">
      <div className="flex items-center justify-between text-[12px]">
        <span className="font-medium">Free trial</span>
        <span className="text-muted-foreground tabular">{remaining} days left</span>
      </div>
      <Progress value={((total - remaining) / total) * 100} className="mt-2 h-1 bg-primary/15" aria-label="Free trial used" />
    </div>
  )
}

export function SidebarContent({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const modules = useVisibleModules()
  const company = useAuthStore((s) => s.company)

  return (
    <div className="flex h-full flex-col">
      <div className={cn('flex h-14 shrink-0 items-center border-b border-sidebar-border', collapsed ? 'justify-center px-2' : 'px-4')}>
        <Logo collapsed={collapsed} />
      </div>

      {!collapsed && company && (
        <div className="mx-3 mt-3 flex items-center gap-2.5 rounded-lg border bg-card px-2.5 py-2 shadow-xs">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary-soft text-[12px] font-semibold text-primary-soft-foreground">
            {company.name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] leading-tight font-medium" title={company.name}>
              {company.name}
            </p>
            <p className="truncate text-[11px] leading-tight text-muted-foreground">{capitalize(company.plan)} plan</p>
          </div>
        </div>
      )}

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
              {items.map((module) => (
                <NavItem key={module.key} module={module} collapsed={collapsed} onNavigate={onNavigate} />
              ))}
            </div>
          )
        })}
      </nav>

      <div className={cn('shrink-0 space-y-2 border-t border-sidebar-border', collapsed ? 'p-2' : 'p-3')}>
        {!collapsed && <TrialCard />}
        <SystemStatus collapsed={collapsed} />
      </div>
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

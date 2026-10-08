import { Check, ChevronRight, Menu, Monitor, Moon, Search, Sun } from 'lucide-react'

import { UserMenu } from '@/components/layout/user-menu'
import { NotificationBell } from '@/features/notifications/bell'
import { MonitoringIndicator } from '@/features/screenshots/components/monitoring-indicator'
import { TopbarTimer } from '@/features/work/components/timer'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Kbd } from '@/components/ui/misc'
import { findModuleByPath } from '@/config/modules'
import { isMac } from '@/lib/utils'
import { useResolvedTheme, useUiStore, type ThemePreference } from '@/stores/ui-store'
import { useLocation } from 'react-router'

const THEME_OPTIONS: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

function ThemeMenu() {
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)
  const resolved = useResolvedTheme()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Change theme">
          {resolved === 'dark' ? <Moon /> : <Sun />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
          <DropdownMenuItem key={value} onSelect={() => setTheme(value)}>
            <Icon /> {label}
            {theme === value && <Check className="ml-auto !text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Breadcrumb() {
  const { pathname } = useLocation()
  const module = findModuleByPath(pathname)
  if (!module) return null
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-[13px] md:flex">
      <span className="text-muted-foreground">{module.section}</span>
      <ChevronRight className="size-3.5 text-muted-foreground/60" />
      <span className="truncate font-medium">{module.label}</span>
    </nav>
  )
}

export function Topbar() {
  const setCommandOpen = useUiStore((s) => s.setCommandOpen)
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen)

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/70 sm:px-6">
      <Button
        variant="ghost"
        size="icon-sm"
        className="lg:hidden"
        onClick={() => setMobileNavOpen(true)}
        aria-label="Open navigation"
      >
        <Menu />
      </Button>
      <Breadcrumb />

      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setCommandOpen(true)}
          className="group flex h-8 items-center gap-2 rounded-md border bg-card px-2.5 text-[13px] text-muted-foreground shadow-xs transition hover:border-input hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none sm:w-60"
          aria-keyshortcuts={isMac ? 'Meta+K' : 'Control+K'}
        >
          <Search className="size-3.5" aria-hidden />
          <span className="sr-only sm:not-sr-only">Search or jump to…</span>
          <span className="ml-auto hidden items-center gap-0.5 sm:flex" aria-hidden>
            <Kbd>{isMac ? '⌘' : 'Ctrl'}</Kbd>
            <Kbd>K</Kbd>
          </span>
        </button>
        <TopbarTimer />
        <MonitoringIndicator />
        <NotificationBell />
        <ThemeMenu />
        <div className="mx-1 h-5 w-px bg-border" aria-hidden />
        <UserMenu />
      </div>
    </header>
  )
}

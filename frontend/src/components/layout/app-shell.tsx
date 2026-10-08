import { Suspense } from 'react'
import { Outlet } from 'react-router'

import { ContentLoader } from '@/components/common/full-page-loader'
import { CommandMenu } from '@/components/layout/command-menu'
import { ConnectionBanner } from '@/components/layout/connection-banner'
import { Sidebar, SidebarContent } from '@/components/layout/sidebar'
import { Topbar } from '@/components/layout/topbar'
import { VerificationBanner } from '@/components/layout/verification-banner'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { useNotificationStream } from '@/features/notifications/meta'
import { useRealtimeConnection } from '@/lib/realtime'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/stores/ui-store'

function MobileNav() {
  const open = useUiStore((s) => s.mobileNavOpen)
  const setOpen = useUiStore((s) => s.setMobileNavOpen)
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="left" className="p-0">
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <SheetDescription className="sr-only">Main application navigation</SheetDescription>
        <SidebarContent onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  )
}

export function AppShell() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed)
  useRealtimeConnection()
  useNotificationStream()

  return (
    <div className="min-h-svh bg-background">
      <Sidebar />
      <MobileNav />
      <div className={cn('flex min-h-svh flex-col transition-[padding] duration-200 ease-out', collapsed ? 'lg:pl-16' : 'lg:pl-64')}>
        <Topbar />
        <ConnectionBanner />
        <VerificationBanner />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-[1280px]">
            <Suspense fallback={<ContentLoader />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
      <CommandMenu />
    </div>
  )
}

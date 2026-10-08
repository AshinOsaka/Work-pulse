import { useEffect, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { FullPageLoader } from '@/components/common/full-page-loader'
import { refreshSession } from '@/lib/api-client'
import { hasSessionHint, useAuthStore, usePermissions } from '@/stores/auth-store'
import type { Permission } from '@/types/api'
import { ForbiddenState } from '@/features/errors/forbidden-state'

/** Restores the session from the refresh cookie once on application start. */
export function useSessionBootstrap() {
  const status = useAuthStore((s) => s.status)

  useEffect(() => {
    if (status !== 'idle') return
    const { setStatus, clearSession } = useAuthStore.getState()
    if (!hasSessionHint()) {
      setStatus('unauthenticated')
      return
    }
    setStatus('loading')
    void refreshSession().then((session) => {
      if (!session) clearSession()
    })
  }, [status])

  return status
}

export function RequireAuth() {
  const status = useAuthStore((s) => s.status)
  const location = useLocation()

  if (status === 'idle' || status === 'loading') return <FullPageLoader />
  if (status === 'unauthenticated') {
    const next = location.pathname + location.search
    return <Navigate to={`/login${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`} replace />
  }
  return <Outlet />
}

export function RedirectIfAuthenticated() {
  const status = useAuthStore((s) => s.status)
  if (status === 'idle' || status === 'loading') return <FullPageLoader />
  if (status === 'authenticated') return <Navigate to="/dashboard" replace />
  return <Outlet />
}

export function RequirePermission({ permission, children }: { permission?: Permission; children: ReactNode }) {
  const { can } = usePermissions()
  if (permission && !can(permission)) return <ForbiddenState permission={permission} />
  return <>{children}</>
}

/** Only allow same-origin relative redirects. */
export function safeNextPath(next: string | null): string {
  if (next && next.startsWith('/') && !next.startsWith('//')) return next
  return '/dashboard'
}

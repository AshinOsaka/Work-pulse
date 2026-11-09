import { create } from 'zustand'

import type { AuthResponse, Company, Permission, SessionResponse, User } from '@/types/api'

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated'

/**
 * The access token lives only in memory. The long-lived refresh token is an
 * httpOnly cookie the browser manages; a non-sensitive localStorage hint lets
 * us skip the refresh round-trip for visitors who were never signed in.
 */
const SESSION_HINT_KEY = 'wp.session'

function writeHint(present: boolean) {
  try {
    if (present) localStorage.setItem(SESSION_HINT_KEY, '1')
    else localStorage.removeItem(SESSION_HINT_KEY)
  } catch {
    /* storage unavailable — the hint is an optimisation only */
  }
}

export function hasSessionHint(): boolean {
  try {
    return localStorage.getItem(SESSION_HINT_KEY) === '1'
  } catch {
    return true
  }
}

/** Why the person was signed out, shown once on the sign-in screen. */
export type SignOutReason = 'password_changed'

interface AuthState {
  status: AuthStatus
  accessToken: string | null
  user: User | null
  company: Company | null
  permissions: Permission[]
  signOutReason: SignOutReason | null
  setStatus: (status: AuthStatus) => void
  setSession: (session: AuthResponse) => void
  updateSession: (session: Partial<SessionResponse>) => void
  /** Sign out locally. A reason (e.g. the password changed) is kept until the sign-in screen has shown it. */
  clearSession: (reason?: SignOutReason) => void
  setSignOutReason: (reason: SignOutReason | null) => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: 'idle',
  accessToken: null,
  user: null,
  company: null,
  permissions: [],
  signOutReason: null,
  setStatus: (status) => set({ status }),
  setSession: (session) => {
    writeHint(true)
    set({
      status: 'authenticated',
      accessToken: session.access_token,
      user: session.user,
      company: session.company,
      permissions: session.permissions,
    })
  },
  updateSession: (session) => set((state) => ({ ...state, ...session })),
  clearSession: (reason) => {
    writeHint(false)
    set((state) => ({
      status: 'unauthenticated',
      accessToken: null,
      user: null,
      company: null,
      permissions: [],
      signOutReason: reason ?? state.signOutReason,
    }))
  },
  setSignOutReason: (signOutReason) => set({ signOutReason }),
}))

export function usePermissions() {
  const permissions = useAuthStore((s) => s.permissions)
  return {
    permissions,
    can: (...required: Permission[]) => required.every((p) => permissions.includes(p)),
  }
}

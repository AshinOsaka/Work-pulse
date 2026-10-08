import { useSyncExternalStore } from 'react'
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type ThemePreference = 'light' | 'dark' | 'system'
export type DashboardMode = 'sample' | 'live'

interface UiState {
  theme: ThemePreference
  sidebarCollapsed: boolean
  commandOpen: boolean
  mobileNavOpen: boolean
  dashboardMode: DashboardMode
  checklistDismissed: boolean
  setDashboardMode: (mode: DashboardMode) => void
  setChecklistDismissed: (dismissed: boolean) => void
  setTheme: (theme: ThemePreference) => void
  toggleSidebar: () => void
  setCommandOpen: (open: boolean) => void
  setMobileNavOpen: (open: boolean) => void
}

const safeStorage = createJSONStorage(() => {
  try {
    return localStorage
  } catch {
    const memory = new Map<string, string>()
    return {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => void memory.set(k, v),
      removeItem: (k: string) => void memory.delete(k),
    }
  }
})

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: 'system',
      sidebarCollapsed: false,
      commandOpen: false,
      mobileNavOpen: false,
      dashboardMode: 'sample',
      checklistDismissed: false,
      setDashboardMode: (dashboardMode) => set({ dashboardMode }),
      setChecklistDismissed: (checklistDismissed) => set({ checklistDismissed }),
      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setCommandOpen: (commandOpen) => set({ commandOpen }),
      setMobileNavOpen: (mobileNavOpen) => set({ mobileNavOpen }),
    }),
    {
      name: 'wp.ui',
      storage: safeStorage,
      partialize: (s) => ({
        theme: s.theme,
        sidebarCollapsed: s.sidebarCollapsed,
        dashboardMode: s.dashboardMode,
        checklistDismissed: s.checklistDismissed,
      }),
    },
  ),
)

const darkQuery = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null

function subscribeSystemTheme(callback: () => void) {
  darkQuery?.addEventListener('change', callback)
  return () => darkQuery?.removeEventListener('change', callback)
}

export function useResolvedTheme(): 'light' | 'dark' {
  const theme = useUiStore((s) => s.theme)
  const systemDark = useSyncExternalStore(subscribeSystemTheme, () => darkQuery?.matches ?? false)
  if (theme === 'system') return systemDark ? 'dark' : 'light'
  return theme
}

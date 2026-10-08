import { useEffect, useState, useSyncExternalStore } from 'react'

/** Current time, re-rendering every `intervalMs` (for live durations and relative times). */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])
  return now
}

const motionQuery = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (callback) => {
      motionQuery?.addEventListener('change', callback)
      return () => motionQuery?.removeEventListener('change', callback)
    },
    () => motionQuery?.matches ?? false,
  )
}

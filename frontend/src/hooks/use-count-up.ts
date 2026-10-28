import { useEffect, useRef, useState } from 'react'

import { usePrefersReducedMotion } from '@/hooks/use-now'

/**
 * Animates a number from its previous value up to `target` with an ease-out curve, for a
 * professional "counting up" effect on stat figures. Returns the current animated value.
 * Honours reduced-motion (jumps straight to the target then).
 */
export function useCountUp(target: number, duration = 800): number {
  const reduced = usePrefersReducedMotion()
  const [value, setValue] = useState(0)
  const fromRef = useRef(0)

  useEffect(() => {
    if (reduced || duration <= 0) {
      fromRef.current = target
      return
    }
    const from = fromRef.current
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3) // ease-out cubic
      setValue(from + (target - from) * eased)
      if (t < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, reduced])

  // While reduced-motion is on (or duration is 0) we show the real value immediately.
  return reduced || duration <= 0 ? target : value
}

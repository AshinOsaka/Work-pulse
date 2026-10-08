/** Small deterministic PRNG (mulberry32) so sample data is stable across reloads. */
export function createRandom(seed: number) {
  let state = seed >>> 0
  const next = () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return {
    next,
    int: (min: number, max: number) => Math.floor(next() * (max - min + 1)) + min,
    chance: (probability: number) => next() < probability,
    pick: <T,>(items: readonly T[]): T => items[Math.floor(next() * items.length)]!,
  }
}

export type Random = ReturnType<typeof createRandom>

/** Stable pseudo-random value in [0, 1) for a string key (e.g. a date). */
export function hashUnit(key: string): number {
  let hash = 2166136261
  for (let i = 0; i < key.length; i++) {
    hash ^= key.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return ((hash >>> 0) % 10_000) / 10_000
}

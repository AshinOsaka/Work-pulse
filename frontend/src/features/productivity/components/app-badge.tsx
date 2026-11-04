import { cn } from '@/lib/utils'

/** Vivid badge colours; the same label always gets the same one (picked from its seed). */
const BADGE_COLORS = [
  'bg-[oklch(0.55_0.22_295)]', // violet
  'bg-[oklch(0.62_0.17_240)]', // blue
  'bg-[oklch(0.68_0.15_158)]', // green
  'bg-[oklch(0.62_0.21_10)]', // rose
  'bg-[oklch(0.76_0.16_75)]', // amber
  'bg-[oklch(0.64_0.19_40)]', // orange
  'bg-[oklch(0.62_0.12_200)]', // teal
  'bg-[oklch(0.58_0.2_330)]', // magenta
]

function badgeColor(seed: string): string {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) | 0
  return BADGE_COLORS[Math.abs(hash) % BADGE_COLORS.length] ?? BADGE_COLORS[0]!
}

const SIZE = {
  sm: 'size-6 rounded-md text-[11px]',
  md: 'size-7 rounded-lg text-[12px]',
  lg: 'size-11 rounded-xl text-[17px]',
} as const

/** Coloured letter badge for an application, website or window title, e.g. "C" for claude.ai. Decorative. */
export function LetterBadge({ label, seed, size = 'md' }: { label: string; seed?: string; size?: keyof typeof SIZE }) {
  const letter = label.replace(/^(https?:\/\/)?(www\.)?/i, '').trim().charAt(0).toUpperCase() || '?'
  return (
    <span
      className={cn('flex shrink-0 items-center justify-center font-semibold text-white shadow-sm', SIZE[size], badgeColor(seed ?? label))}
      aria-hidden
    >
      {letter}
    </span>
  )
}

import { Link } from 'react-router'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { cn, initials } from '@/lib/utils'

/** Deterministic, low-saturation avatar tints so people are visually distinct. */
const TINTS = [
  'from-[oklch(0.62_0.17_277)] to-[oklch(0.55_0.19_300)]',
  'from-[oklch(0.62_0.13_200)] to-[oklch(0.55_0.15_230)]',
  'from-[oklch(0.65_0.13_160)] to-[oklch(0.56_0.13_185)]',
  'from-[oklch(0.68_0.14_60)] to-[oklch(0.6_0.16_35)]',
  'from-[oklch(0.62_0.16_350)] to-[oklch(0.55_0.18_320)]',
]

function tint(seed: string): string {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) | 0
  return TINTS[Math.abs(hash) % TINTS.length] ?? TINTS[0]!
}

export function PersonAvatar({
  name,
  seed,
  className,
  'aria-hidden': hidden,
}: {
  name: string
  seed?: string
  className?: string
  /** Set when the name is shown next to the avatar, so the initials aren't read twice. */
  'aria-hidden'?: boolean
}) {
  return (
    <Avatar className={cn('size-8', className)} aria-hidden={hidden}>
      <AvatarFallback className={cn('bg-gradient-to-br', tint(seed ?? name))}>{initials(name)}</AvatarFallback>
    </Avatar>
  )
}

interface PersonProps {
  id: string
  name: string
  subtitle?: string | null
  link?: boolean
  size?: 'sm' | 'md'
}

export function Person({ id, name, subtitle, link = true, size = 'md' }: PersonProps) {
  const content = (
    <span className="flex min-w-0 items-center gap-2.5">
      <PersonAvatar name={name} seed={id} className={size === 'sm' ? 'size-6 text-[10px]' : undefined} />
      <span className="min-w-0">
        <span className="block truncate font-medium text-foreground">{name}</span>
        {subtitle && <span className="block truncate text-[12px] text-muted-foreground">{subtitle}</span>}
      </span>
    </span>
  )
  if (!link) return content
  return (
    <Link to={`/people/employees/${id}`} className="rounded-md hover:[&_span.font-medium]:text-primary">
      {content}
    </Link>
  )
}

const GROUP_SIZE = {
  xs: 'size-5 text-[8px]',
  sm: 'size-6 text-[9px]',
  md: 'size-7 text-[10px]',
} as const

/** Overlapping avatars for a group (assignees, project members), with "+N" for the rest and every name on hover. */
export function AvatarGroup({
  people,
  max = 5,
  size = 'sm',
  className,
}: {
  people: { id: string; full_name: string }[]
  max?: number
  size?: keyof typeof GROUP_SIZE
  className?: string
}) {
  if (!people.length) return null
  const names = people.map((p) => p.full_name).join(', ')
  const rest = people.length - max
  return (
    <span className={cn('flex', size === 'md' ? '-space-x-1' : '-space-x-1.5', className)} title={names}>
      <span className="sr-only">{names}</span>
      {people.slice(0, max).map((p) => (
        <PersonAvatar key={p.id} name={p.full_name} seed={p.id} className={cn(GROUP_SIZE[size], 'ring-2 ring-card')} aria-hidden />
      ))}
      {rest > 0 && (
        <span className={cn('flex items-center justify-center rounded-full bg-muted font-medium text-muted-foreground ring-2 ring-card', GROUP_SIZE[size])} aria-hidden>
          +{rest}
        </span>
      )}
    </span>
  )
}

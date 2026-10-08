import { cn } from '@/lib/utils'

/** Mirrors the backend policy: ≥10 characters with at least one letter and one number. */
export function passwordIssues(password: string): string | null {
  if (password.length < 10) return 'Use at least 10 characters.'
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return 'Include at least one letter and one number.'
  return null
}

function score(password: string): number {
  if (!password) return 0
  let points = 0
  if (password.length >= 10) points++
  if (password.length >= 14) points++
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) points++
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) points++
  return Math.max(1, points)
}

const LABELS = ['', 'Weak', 'Fair', 'Good', 'Strong']
const COLORS = ['', 'bg-destructive', 'bg-warning', 'bg-info', 'bg-success']

export function PasswordStrength({ password }: { password: string }) {
  const value = score(password)
  if (!password) return <span>At least 10 characters, with a letter and a number.</span>
  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-1 gap-1" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={cn('h-1 flex-1 rounded-full bg-muted transition-colors', i <= value && COLORS[value])} />
        ))}
      </div>
      <span className="w-12 text-right text-[12px] font-medium">{LABELS[value]}</span>
    </div>
  )
}

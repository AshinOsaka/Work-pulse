import { useId, useState, type ReactNode } from 'react'
import { Eye, EyeOff, TriangleAlert } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface FieldProps extends Omit<React.ComponentProps<'input'>, 'id'> {
  label: string
  error?: string
  hint?: ReactNode
  labelAction?: ReactNode
}

export function FormField({ label, error, hint, labelAction, className, ...props }: FieldProps) {
  const id = useId()
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{label}</Label>
        {labelAction}
      </div>
      <Input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        {...props}
      />
      <FieldMessage id={`${id}-error`} error={error} hint={hint} />
    </div>
  )
}

export function PasswordField({ label, error, hint, labelAction, className, ...props }: FieldProps) {
  const id = useId()
  const [visible, setVisible] = useState(false)
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{label}</Label>
        {labelAction}
      </div>
      <div className="relative">
        <Input
          id={id}
          type={visible ? 'text' : 'password'}
          className="pr-10"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground transition hover:text-foreground"
          aria-label={visible ? 'Hide password' : 'Show password'}
          tabIndex={-1}
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
      <FieldMessage id={`${id}-error`} error={error} hint={hint} />
    </div>
  )
}

function FieldMessage({ id, error, hint }: { id: string; error?: string; hint?: ReactNode }) {
  if (error) {
    return (
      <p id={id} className="flex items-center gap-1.5 text-[12px] text-destructive animate-in fade-in-0">
        <TriangleAlert className="size-3.5 shrink-0" />
        {error}
      </p>
    )
  }
  if (hint) return <div className="text-[12px] text-muted-foreground">{hint}</div>
  return null
}

export function FormAlert({ children, tone = 'error' }: { children: ReactNode; tone?: 'error' | 'success' | 'info' }) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'rounded-lg border px-3.5 py-2.5 text-[13px] animate-in fade-in-0 slide-in-from-top-1',
        tone === 'error' && 'border-destructive/25 bg-destructive-soft text-destructive',
        tone === 'success' && 'border-success/25 bg-success-soft text-success',
        tone === 'info' && 'border-info/25 bg-info-soft text-info',
      )}
    >
      {children}
    </div>
  )
}

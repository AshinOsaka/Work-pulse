import { useId, useState, type KeyboardEvent } from 'react'
import { Tag, X } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { labelTone, MAX_LABELS, normalizeLabel } from '@/features/work/meta'
import { cn } from '@/lib/utils'

export function LabelChip({ label, onRemove, className }: { label: string; onRemove?: () => void; className?: string }) {
  return (
    <span className={cn('inline-flex max-w-full items-center gap-1 rounded px-1.5 py-0.5 text-[11px] leading-none font-medium', labelTone(label), className)}>
      <span className="truncate">{label}</span>
      {onRemove && (
        <button type="button" onClick={onRemove} aria-label={`Remove label ${label}`} className="-mr-0.5 rounded-sm opacity-60 hover:opacity-100">
          <X className="size-3" aria-hidden />
        </button>
      )}
    </span>
  )
}

/** Compact label row for cards and lists; extra labels collapse into "+n". */
export function LabelChips({ labels, max = 3, className }: { labels: string[]; max?: number; className?: string }) {
  if (!labels.length) return null
  return (
    <span className={cn('flex min-w-0 flex-wrap gap-1', className)}>
      <span className="sr-only">Labels:</span>
      {labels.slice(0, max).map((l) => (
        <LabelChip key={l} label={l} />
      ))}
      {labels.length > max && <span className="text-[11px] text-muted-foreground">+{labels.length - max}</span>}
    </span>
  )
}

/** Add labels by typing (Enter or comma), pick from the project's existing labels, remove with ×. */
export function LabelEditor({
  value,
  onChange,
  suggestions,
  disabled,
}: {
  value: string[]
  onChange: (labels: string[]) => void
  suggestions: string[]
  disabled?: boolean
}) {
  const [draft, setDraft] = useState('')
  const listId = useId()
  const full = value.length >= MAX_LABELS

  const add = (raw: string) => {
    const label = normalizeLabel(raw.replace(/,/g, ' '))
    setDraft('')
    if (!label || value.includes(label) || full) return
    onChange([...value, label])
  }
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add(draft)
    } else if (e.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className="flex min-h-8 flex-wrap items-center gap-1.5">
      {value.map((l) => (
        <LabelChip key={l} label={l} onRemove={disabled ? undefined : () => onChange(value.filter((x) => x !== l))} />
      ))}
      {!disabled && !full && (
        <div className="relative min-w-32 flex-1">
          <Tag className="pointer-events-none absolute top-1/2 left-2 size-3 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={draft}
            onChange={(e) => {
              // A picked suggestion arrives as the full value: add it straight away.
              const next = e.target.value
              if (suggestions.includes(next) && !value.includes(next)) add(next)
              else setDraft(next)
            }}
            onKeyDown={onKeyDown}
            onBlur={() => draft.trim() && add(draft)}
            list={listId}
            placeholder={value.length ? 'Add label' : 'Add labels…'}
            aria-label="Add a label"
            className="h-7 pl-6 text-[12px]"
            maxLength={30}
          />
          <datalist id={listId}>
            {suggestions
              .filter((s) => !value.includes(s))
              .map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
          </datalist>
        </div>
      )}
      {disabled && value.length === 0 && <span className="text-[13px] text-muted-foreground">None</span>}
    </div>
  )
}

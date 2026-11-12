import { useState, type KeyboardEvent } from 'react'
import { AppWindow, Check, ChevronDown, Globe, Plus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CATEGORY } from '@/features/productivity/meta'
import { cn } from '@/lib/utils'
import type { ProductivityCategory, RuleKind, TemplateRule } from '@/types/api'

const CATEGORIES: ProductivityCategory[] = ['productive', 'neutral', 'unproductive']

/** The same clean-up the server applies: lower case, and a pasted URL becomes its domain without "www.". */
export function normalisePattern(value: string): string {
  let v = value.trim().toLowerCase()
  if (v.startsWith('http://') || v.startsWith('https://')) v = v.split('://')[1] ?? ''
  v = v.split('/')[0] ?? ''
  return v.startsWith('www.') ? v.slice(4) : v
}

export const ruleKey = (r: Pick<TemplateRule, 'kind' | 'pattern'>) => `${r.kind}:${r.pattern}`

/** Guess the type while typing: "something.exe" is an application, "example.com" a website. */
function guessKind(value: string): RuleKind | null {
  const v = value.trim().toLowerCase()
  if (v.endsWith('.exe')) return 'app'
  if (/^(https?:\/\/)?[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(\/.*)?$/.test(v)) return 'website'
  return null
}

/** One application or website rule as a chip; the chip opens a menu to change its category. */
function RuleChip({
  rule,
  disabled,
  onCategory,
  onRemove,
}: {
  rule: TemplateRule
  disabled?: boolean
  onCategory: (category: ProductivityCategory) => void
  onRemove: () => void
}) {
  const KindIcon = rule.kind === 'app' ? AppWindow : Globe
  return (
    <li className="inline-flex items-center rounded-md border bg-card text-[12px] shadow-xs">
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          className="inline-flex items-center gap-1.5 rounded-l-md py-1 pr-1 pl-2 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
          aria-label={`${rule.pattern}: ${CATEGORY[rule.category].label}. Change category`}
        >
          <span className={cn('size-2 shrink-0 rounded-sm', CATEGORY[rule.category].swatch)} aria-hidden />
          <KindIcon className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          <span className="max-w-48 truncate">{rule.pattern}</span>
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-44">
          <DropdownMenuLabel className="max-w-56 truncate">{rule.pattern}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {CATEGORIES.map((c) => (
            <DropdownMenuItem key={c} onSelect={() => c !== rule.category && onCategory(c)}>
              <span className={cn('size-2 rounded-sm', CATEGORY[c].swatch)} aria-hidden />
              {CATEGORY[c].label}
              {c === rule.category && <Check className="ml-auto size-3.5" aria-hidden />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={onRemove} className="text-destructive focus:text-destructive">
            <X className="size-3.5" aria-hidden /> Remove
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <button
        type="button"
        disabled={disabled}
        onClick={onRemove}
        aria-label={`Remove ${rule.pattern}`}
        className="inline-flex h-full items-center rounded-r-md border-l px-1.5 py-1 text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
      >
        <X className="size-3" aria-hidden />
      </button>
    </li>
  )
}

/**
 * A list of application and website rules that can be added to, re-categorised and removed. Used for templates
 * and new profiles (local edits) and for an existing profile's rules (saved as you go).
 */
export function RuleListEditor({
  rules,
  onAdd,
  onCategory,
  onRemove,
  disabled,
  idPrefix,
  className,
}: {
  rules: TemplateRule[]
  onAdd: (rule: TemplateRule) => void
  onCategory: (rule: TemplateRule, category: ProductivityCategory) => void
  onRemove: (rule: TemplateRule) => void
  disabled?: boolean
  idPrefix: string
  className?: string
}) {
  const [kind, setKind] = useState<RuleKind>('website')
  const [value, setValue] = useState('')
  const [category, setCategory] = useState<ProductivityCategory>('productive')
  const [error, setError] = useState<string | null>(null)

  const type = (next: string) => {
    setValue(next)
    setError(null)
    const guess = guessKind(next)
    if (guess) setKind(guess)
  }
  const add = () => {
    const pattern = normalisePattern(value)
    if (!pattern) return setError(kind === 'app' ? 'Enter an application, such as tally.exe.' : 'Enter a website, such as example.com.')
    if (kind === 'website' && (!pattern.includes('.') || pattern.includes(' '))) return setError('Enter a domain such as example.com.')
    const existing = rules.find((r) => r.kind === kind && r.pattern === pattern)
    if (existing) {
      if (existing.category !== category) onCategory(existing, category)
    } else {
      onAdd({ kind, pattern, category })
    }
    setValue('')
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault() // never submit the surrounding form
      add()
    }
  }

  const sorted = [...rules].sort((a, b) => CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category) || a.pattern.localeCompare(b.pattern))
  const counts = CATEGORIES.map((c) => ({ c, n: rules.filter((r) => r.category === c).length }))

  return (
    <div className={cn('space-y-2', className)}>
      <div className="rounded-lg border bg-subtle">
        {sorted.length ? (
          <ul className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto p-2" aria-label="Rules">
            {sorted.map((r) => (
              <RuleChip key={ruleKey(r)} rule={r} disabled={disabled} onCategory={(c) => onCategory(r, c)} onRemove={() => onRemove(r)} />
            ))}
          </ul>
        ) : (
          <p className="px-3 py-4 text-center text-[12px] text-muted-foreground">No rules yet. Add an application or website below.</p>
        )}
        <div className="flex flex-wrap items-start gap-2 border-t p-2">
          <Select value={kind} onValueChange={(v) => setKind(v as RuleKind)} disabled={disabled}>
            <SelectTrigger size="sm" className="w-32 bg-card" aria-label="Type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="website">Website</SelectItem>
              <SelectItem value="app">Application</SelectItem>
            </SelectContent>
          </Select>
          <div className="min-w-40 flex-1">
            <Input
              id={`${idPrefix}-pattern`}
              value={value}
              onChange={(e) => type(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={disabled}
              placeholder={kind === 'app' ? 'e.g. tally.exe' : 'e.g. amadeus.com'}
              aria-label={kind === 'app' ? 'Application' : 'Website'}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${idPrefix}-error` : undefined}
              maxLength={253}
              className="h-8 text-[13px]"
            />
          </div>
          <Select value={category} onValueChange={(v) => setCategory(v as ProductivityCategory)} disabled={disabled}>
            <SelectTrigger size="sm" className="w-36 bg-card" aria-label="Category">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c}>
                  <span className={cn('size-2 rounded-sm', CATEGORY[c].swatch)} aria-hidden />
                  {CATEGORY[c].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="button" size="sm" variant="outline" onClick={add} disabled={disabled || !value.trim()}>
            <Plus /> Add
          </Button>
        </div>
      </div>
      {error && (
        <p id={`${idPrefix}-error`} role="alert" className="text-[12px] text-destructive">
          {error}
        </p>
      )}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {counts.map(({ c, n }) => (
          <span key={c} className="inline-flex items-center gap-1">
            <span className={cn('size-2 rounded-sm', CATEGORY[c].swatch)} aria-hidden />
            {CATEGORY[c].label} <span className="tabular">{n}</span>
          </span>
        ))}
        <span>· Click a rule to change its category.</span>
      </p>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, X } from 'lucide-react'

import { PersonAvatar } from '@/components/common/person'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useEmployeeOptions, useEmployeeSearch } from '@/features/people/api'
import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { cn } from '@/lib/utils'

interface EmployeePickerProps {
  id?: string
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  /** Ids that cannot be chosen (e.g. the employee being edited). */
  exclude?: string[]
  invalid?: boolean
  /** Display name for the current value when it is not in the option list. */
  fallbackLabel?: string
}

const MAX_SHOWN = 50

/** Searchable employee combobox used for managers, team leads and department heads. */
export function EmployeePicker({
  id,
  value,
  onChange,
  placeholder = 'Select a person',
  exclude = [],
  invalid,
  fallbackLabel,
}: EmployeePickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const term = useDebouncedValue(query.trim())
  const options = useEmployeeOptions(true)
  // Typing searches the server, so everyone in scope can be found however large the company (the initial list is
  // capped); either way only a bounded number of rows is rendered, so the picker stays instant.
  const searched = useEmployeeSearch(term)
  const source = term ? searched : options
  const { choices, more } = useMemo(() => {
    const matching = (source.data ?? []).filter((o) => !exclude.includes(o.id))
    return { choices: matching.slice(0, MAX_SHOWN), more: Math.max(0, matching.length - MAX_SHOWN) }
  }, [source.data, exclude])
  const selected = options.data?.find((o) => o.id === value)
  const label = selected?.full_name ?? (value ? fallbackLabel : undefined)

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setQuery('')
      }}
    >
      <div className="relative">
        <PopoverTrigger
          id={id}
          aria-invalid={invalid || undefined}
          className={cn(
            'flex h-9 w-full items-center gap-2 rounded-md border border-input bg-card px-3 text-left text-sm shadow-xs transition outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25 aria-invalid:border-destructive',
            !label && 'text-muted-foreground',
          )}
        >
          {label ? (
            <>
              <PersonAvatar name={label} seed={value ?? undefined} className="size-5 text-[9px]" />
              <span className="truncate">{label}</span>
            </>
          ) : (
            <span className="truncate">{placeholder}</span>
          )}
          <ChevronsUpDown className={cn('ml-auto size-4 shrink-0 opacity-50', value && 'mr-6')} />
        </PopoverTrigger>
        {value && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="absolute top-1/2 right-8 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Clear selection"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-64 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search people…" value={query} onValueChange={setQuery} />
          <CommandList className="max-h-64">
            <CommandEmpty>{source.isFetching || options.isPending ? 'Searching…' : 'No matching people.'}</CommandEmpty>
            <CommandGroup>
              {choices.map((option) => (
                <CommandItem
                  key={option.id}
                  value={`${option.full_name} ${option.email} ${option.id}`}
                  onSelect={() => {
                    onChange(option.id)
                    setOpen(false)
                  }}
                >
                  <PersonAvatar name={option.full_name} seed={option.id} className="size-6 text-[10px]" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{option.full_name}</span>
                    {option.job_title && (
                      <span className="block truncate text-[11px] text-muted-foreground">{option.job_title}</span>
                    )}
                  </span>
                  {option.id === value && <Check className="size-4 !text-primary" />}
                </CommandItem>
              ))}
            </CommandGroup>
            {more > 0 && (
              <p className="px-3 py-2 text-[12px] text-muted-foreground" aria-live="polite">
                {term ? `${more} more matches — keep typing to narrow them` : 'Type a name or e-mail to search everyone'}
              </p>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

import { useState } from 'react'
import { Check, UserPlus } from 'lucide-react'

import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { EmployeeRef } from '@/types/api'

/** Multi-select of project members. */
export function AssigneePicker({
  members,
  value,
  onChange,
  disabled,
  label = 'Assignees',
  placeholder = 'Assign',
}: {
  members: EmployeeRef[]
  value: string[]
  onChange: (ids: string[]) => void
  disabled?: boolean
  label?: string
  /** Shown when nobody is selected. */
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const selected = members.filter((m) => value.includes(m.id))
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-auto min-h-8 justify-start py-1" disabled={disabled}>
          <span className="sr-only">{label}: </span>
          {selected.length ? (
            <span className="flex flex-wrap items-center gap-1.5">
              {selected.map((m) => (
                <span key={m.id} className="inline-flex items-center gap-1 rounded-full bg-muted py-0.5 pr-2 pl-0.5 text-[12px]">
                  <PersonAvatar name={m.full_name} seed={m.id} className="size-5 text-[8px]" aria-hidden />
                  {m.full_name}
                </span>
              ))}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">
              <UserPlus aria-hidden /> {placeholder}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <Command>
          <CommandInput placeholder="Find a member…" />
          <CommandList>
            <CommandEmpty>No project members match.</CommandEmpty>
            <CommandGroup>
              {members.map((m) => (
                <CommandItem key={m.id} value={m.full_name} onSelect={() => toggle(m.id)}>
                  <PersonAvatar name={m.full_name} seed={m.id} className="size-5 text-[8px]" />
                  <span className="flex-1 truncate">{m.full_name}</span>
                  <Check className={cn('size-4', value.includes(m.id) ? 'opacity-100' : 'opacity-0')} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

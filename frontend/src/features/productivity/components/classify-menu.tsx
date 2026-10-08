import { ChevronDown } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useCreateRule } from '@/features/productivity/api'
import { CATEGORY } from '@/features/productivity/meta'
import { errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { ProductivityCategory, RuleKind } from '@/types/api'

/** Quick company-wide classification; finer rules (department, team, role) live on the Rules page. */
export function ClassifyMenu({ kind, pattern, name }: { kind: RuleKind; pattern: string; name: string }) {
  const create = useCreateRule()
  const classify = (category: ProductivityCategory) =>
    create.mutate(
      { kind, pattern, category, scope: 'company' },
      {
        onSuccess: () => toast.success(`${name} is now ${CATEGORY[category].label.toLowerCase()} for the whole company`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline" className="h-7 text-[12px]" loading={create.isPending}>
          Classify <ChevronDown />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel className="text-[11px] text-muted-foreground">Company-wide rule for {name}</DropdownMenuLabel>
        {(['productive', 'neutral', 'unproductive'] as const).map((category) => (
          <DropdownMenuItem key={category} onSelect={() => classify(category)}>
            <span className={cn('size-2.5 rounded-sm', CATEGORY[category].swatch)} aria-hidden />
            {CATEGORY[category].label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

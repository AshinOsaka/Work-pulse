import * as React from 'react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'

import { cn } from '@/lib/utils'

function RadioGroup({ className, ...props }: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return <RadioGroupPrimitive.Root data-slot="radio-group" className={cn('grid gap-2', className)} {...props} />
}

/** A card-like selectable option (segmented choices, theme pickers). */
function RadioCard({ className, ...props }: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-card"
      className={cn(
        'rounded-md border bg-card text-muted-foreground transition outline-none hover:border-input hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40',
        'data-[state=checked]:border-primary data-[state=checked]:text-foreground data-[state=checked]:ring-[3px] data-[state=checked]:ring-primary/15',
        className,
      )}
      {...props}
    />
  )
}

export { RadioGroup, RadioCard }

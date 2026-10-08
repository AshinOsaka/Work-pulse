import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

interface SegmentedControlProps<T extends string> {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string; icon?: LucideIcon }[]
  label: string
  size?: 'sm' | 'default'
  className?: string
}

/** Compact single-choice toggle built on Radix RadioGroup (arrow-key navigation included). */
export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
  size = 'default',
  className,
}: SegmentedControlProps<T>) {
  return (
    <RadioGroupPrimitive.Root
      value={value}
      onValueChange={(v) => onChange(v as T)}
      aria-label={label}
      className={cn('inline-flex items-center rounded-lg border bg-muted/60 p-0.5', className)}
    >
      {options.map(({ value: optionValue, label: optionLabel, icon: Icon }) => (
        <RadioGroupPrimitive.Item
          key={optionValue}
          value={optionValue}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md font-medium text-muted-foreground transition-all outline-none',
            'hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40',
            'data-[state=checked]:bg-card data-[state=checked]:text-foreground data-[state=checked]:shadow-xs',
            size === 'sm' ? 'h-6 px-2 text-[12px]' : 'h-7 px-3 text-[13px]',
          )}
        >
          {Icon && <Icon className="size-3.5" />}
          {optionLabel}
        </RadioGroupPrimitive.Item>
      ))}
    </RadioGroupPrimitive.Root>
  )
}

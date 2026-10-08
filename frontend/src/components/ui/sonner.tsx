import { Toaster as Sonner, type ToasterProps } from 'sonner'

import { useResolvedTheme } from '@/stores/ui-store'

function Toaster(props: ToasterProps) {
  const theme = useResolvedTheme()
  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      closeButton
      toastOptions={{
        classNames: {
          toast:
            '!rounded-lg !border !border-border !bg-popover !text-popover-foreground !shadow-elevated !text-[13px]',
          description: '!text-muted-foreground',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }

import { Spinner } from '@/components/ui/misc'
import { LogoMark } from '@/components/common/logo'

export function FullPageLoader({ label = 'Loading your workspace…' }: { label?: string }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-background" aria-live="polite" aria-busy="true">
      <LogoMark className="size-10 animate-pulse" />
      <p className="text-[13px] text-muted-foreground">{label}</p>
    </div>
  )
}

export function ContentLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center" aria-live="polite" aria-busy="true" aria-label="Loading">
      <Spinner className="size-5 text-primary" />
    </div>
  )
}

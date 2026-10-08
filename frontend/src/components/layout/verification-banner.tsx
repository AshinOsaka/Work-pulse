import { MailWarning } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { useResendVerification } from '@/features/auth/api'
import { useHealth } from '@/hooks/use-system'
import { errorMessage } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'

export function VerificationBanner() {
  const user = useAuthStore((s) => s.user)
  const resend = useResendVerification()
  const health = useHealth()
  if (!user || user.email_verified) return null

  const nonProduction = health.data && health.data.environment !== 'production'

  return (
    <div className="flex flex-col gap-2 border-b bg-warning-soft/70 px-4 py-2.5 text-[13px] sm:flex-row sm:items-center sm:px-6">
      <div className="flex min-w-0 items-start gap-2.5 sm:items-center">
        <MailWarning className="mt-0.5 size-4 shrink-0 text-warning sm:mt-0" />
        <p className="min-w-0">
          <span className="font-medium">Verify your email address.</span>{' '}
          <span className="text-muted-foreground">
            We sent a link to {user.email}.
            {nonProduction && ' In this environment, emails are written to the API server log.'}
          </span>
        </p>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="shrink-0 self-start sm:ml-auto sm:self-auto"
        loading={resend.isPending}
        onClick={() =>
          resend.mutate(undefined, {
            onSuccess: (r) => toast.success(r.message),
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        Resend link
      </Button>
    </div>
  )
}

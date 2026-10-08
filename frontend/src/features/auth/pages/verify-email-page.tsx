import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { CircleCheck, MailX } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { Spinner } from '@/components/ui/misc'
import { Button } from '@/components/ui/button'
import { authApi } from '@/features/auth/api'
import { AuthLayout } from '@/features/auth/components/auth-layout'
import { ApiError, errorMessage } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)
  const updateSession = useAuthStore((s) => s.updateSession)
  const verify = useMutation({ mutationFn: authApi.verifyEmail })
  const started = useRef(false)

  useEffect(() => {
    // Tokens are single-use: guard against React StrictMode's double effect.
    if (!token || started.current) return
    started.current = true
    verify.mutate(token)
  }, [token, verify])

  useEffect(() => {
    if (verify.isSuccess && user && !user.email_verified) updateSession({ user: { ...user, email_verified: true } })
  }, [verify.isSuccess, user, updateSession])

  const continueAction = (
    <Button asChild className="mt-6 w-full">
      <Link to={status === 'authenticated' ? '/dashboard' : '/login'}>
        {status === 'authenticated' ? 'Go to dashboard' : 'Continue to sign in'}
      </Link>
    </Button>
  )

  if (!token || verify.isError) {
    return (
      <AuthLayout title="Verification failed">
        <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-destructive-soft text-destructive">
          <MailX className="size-5" />
        </div>
        <p className="text-sm text-muted-foreground">
          {!token ? 'This verification link is incomplete.' : verify.error instanceof ApiError && verify.error.status === 422 ? 'This verification link is invalid.' : errorMessage(verify.error)} You can request a new link from
          the banner in your workspace after signing in.
        </p>
        {continueAction}
      </AuthLayout>
    )
  }

  if (verify.isSuccess) {
    return (
      <AuthLayout title="Email verified">
        <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-success-soft text-success">
          <CircleCheck className="size-5" />
        </div>
        <p className="text-sm text-muted-foreground">Thanks for confirming your email address. Your account is now fully set up.</p>
        {continueAction}
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Verifying your email">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <Spinner className="text-primary" /> Confirming your verification link…
      </div>
    </AuthLayout>
  )
}

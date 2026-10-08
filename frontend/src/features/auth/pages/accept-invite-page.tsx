import { useState, type FormEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { MailX } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Spinner } from '@/components/ui/misc'
import { FormAlert, FormField, PasswordField } from '@/components/common/form-field'
import { passwordIssues, PasswordStrength } from '@/components/common/password-strength'
import { Button } from '@/components/ui/button'
import { AuthLayout } from '@/features/auth/components/auth-layout'
import { api, ApiError, errorMessage } from '@/lib/api-client'
import { queryClient } from '@/lib/query-client'
import { useAuthStore } from '@/stores/auth-store'
import type { AuthResponse, InvitationPreview } from '@/types/api'

export function AcceptInvitePage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)
  const accept = useMutation({
    mutationFn: (body: { token: string; password: string; full_name?: string }) =>
      api.post<AuthResponse>('/auth/invitations/accept', body, { auth: false }),
  })
  const preview = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => api.get<InvitationPreview>(`/auth/invitations/${encodeURIComponent(token)}`, { auth: false }),
    // The token is single-use: never re-check it once acceptance has started.
    enabled: Boolean(token) && accept.isIdle,
    retry: false,
    staleTime: Infinity,
  })
  const [name, setName] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  if (!token || preview.isError) {
    return (
      <AuthLayout title="Invitation unavailable">
        <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-destructive-soft text-destructive">
          <MailX className="size-5" />
        </div>
        <p className="text-sm text-muted-foreground">
          {token ? errorMessage(preview.error) : 'This invitation link is incomplete.'} Ask your workspace administrator to
          send a new invitation.
        </p>
        <Button asChild variant="outline" className="mt-6 w-full">
          <Link to="/login">Go to sign in</Link>
        </Button>
      </AuthLayout>
    )
  }

  if (preview.isPending) {
    return (
      <AuthLayout title="Checking your invitation">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner className="text-primary" /> One moment…
        </div>
      </AuthLayout>
    )
  }

  const invitation = preview.data
  const fullName = name ?? invitation.full_name
  const serverErrors = accept.error instanceof ApiError ? accept.error.fieldErrors : {}

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const issues: Record<string, string> = {}
    const issue = passwordIssues(password)
    if (issue) issues.password = issue
    if (password !== confirm) issues.confirm = 'Passwords do not match.'
    if (fullName.trim().length < 2) issues.full_name = 'Enter your full name.'
    setErrors(issues)
    if (Object.keys(issues).length) return
    accept.mutate(
      { token, password, full_name: fullName.trim() !== invitation.full_name ? fullName.trim() : undefined },
      {
        onSuccess: (session) => {
          queryClient.clear()
          setSession(session)
          toast.success(`Welcome to ${invitation.company_name}`)
          navigate('/dashboard', { replace: true })
        },
      },
    )
  }

  return (
    <AuthLayout
      title={`Join ${invitation.company_name}`}
      description={
        <>
          You've been invited to WorkPulse as <span className="font-medium text-foreground">{invitation.email}</span>.
          Set a password to activate your account.
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {accept.error && !Object.keys(serverErrors).length && <FormAlert>{errorMessage(accept.error)}</FormAlert>}
        <FormField
          label="Full name"
          autoComplete="name"
          value={fullName}
          onChange={(e) => setName(e.target.value)}
          error={errors.full_name ?? serverErrors.full_name}
        />
        <PasswordField
          label="Password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password ?? serverErrors.password}
          hint={<PasswordStrength password={password} />}
        />
        <PasswordField
          label="Confirm password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
        />
        <Button type="submit" className="w-full" size="lg" loading={accept.isPending}>
          Activate account
        </Button>
      </form>
    </AuthLayout>
  )
}

import { useState, type FormEvent } from 'react'
import { ArrowLeft, KeyRound, MailCheck } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { useForgotPassword, useResetPassword } from '@/features/auth/api'
import { AuthLayout } from '@/features/auth/components/auth-layout'
import { FormAlert, FormField, PasswordField } from '@/components/common/form-field'
import { passwordIssues, PasswordStrength } from '@/components/common/password-strength'
import { ApiError, errorMessage } from '@/lib/api-client'

function BackToLogin() {
  return (
    <Link to="/login" className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline">
      <ArrowLeft className="size-3.5" /> Back to sign in
    </Link>
  )
}

function ResultIcon({ icon: Icon }: { icon: typeof MailCheck }) {
  return (
    <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-primary-soft text-primary">
      <Icon className="size-5" />
    </div>
  )
}

export function ForgotPasswordPage() {
  const forgot = useForgotPassword()
  const [email, setEmail] = useState('')
  const fieldErrors = forgot.error instanceof ApiError ? forgot.error.fieldErrors : {}

  if (forgot.isSuccess) {
    return (
      <AuthLayout title="Check your email" footer={<BackToLogin />}>
        <ResultIcon icon={MailCheck} />
        <p className="text-sm text-muted-foreground">
          If an account exists for <span className="font-medium text-foreground">{email}</span>, you'll receive a link to
          reset your password shortly. The link expires in 30 minutes.
        </p>
        <Button variant="outline" className="mt-6 w-full" onClick={() => forgot.reset()}>
          Use a different email
        </Button>
      </AuthLayout>
    )
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    forgot.mutate(email)
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter your work email and we'll send you a secure reset link."
      footer={<BackToLogin />}
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {forgot.error && !fieldErrors.email && <FormAlert>{errorMessage(forgot.error)}</FormAlert>}
        <FormField
          label="Work email"
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
        />
        <Button type="submit" className="w-full" size="lg" loading={forgot.isPending} disabled={!email}>
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const navigate = useNavigate()
  const reset = useResetPassword()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [clientError, setClientError] = useState<Record<string, string>>({})

  if (!token) {
    return (
      <AuthLayout title="Invalid reset link" footer={<BackToLogin />}>
        <ResultIcon icon={KeyRound} />
        <p className="text-sm text-muted-foreground">
          This password reset link is missing its token. Request a new link to continue.
        </p>
        <Button asChild className="mt-6 w-full">
          <Link to="/forgot-password">Request a new link</Link>
        </Button>
      </AuthLayout>
    )
  }

  const serverFieldErrors = reset.error instanceof ApiError ? reset.error.fieldErrors : {}

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const issues: Record<string, string> = {}
    const issue = passwordIssues(password)
    if (issue) issues.password = issue
    if (password !== confirm) issues.confirm = 'Passwords do not match.'
    setClientError(issues)
    if (Object.keys(issues).length) return
    reset.mutate(
      { token, password },
      {
        onSuccess: (r) => {
          toast.success(r.message)
          navigate('/login', { replace: true })
        },
      },
    )
  }

  return (
    <AuthLayout title="Choose a new password" description="For your security, all other sessions will be signed out." footer={<BackToLogin />}>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {reset.error && !Object.keys(serverFieldErrors).length && (
          <FormAlert>
            {errorMessage(reset.error)}{' '}
            <Link to="/forgot-password" className="font-medium underline">
              Request a new link
            </Link>
          </FormAlert>
        )}
        <PasswordField
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={clientError.password ?? serverFieldErrors.password}
          hint={<PasswordStrength password={password} />}
        />
        <PasswordField
          label="Confirm new password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={clientError.confirm}
        />
        <Button type="submit" className="w-full" size="lg" loading={reset.isPending}>
          Update password
        </Button>
      </form>
    </AuthLayout>
  )
}

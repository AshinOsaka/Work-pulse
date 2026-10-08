import { useState, type FormEvent } from 'react'
import { ShieldCheck } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { useLogin, useVerifyMfa } from '@/features/auth/api'
import { AuthLayout } from '@/features/auth/components/auth-layout'
import { FormAlert, FormField, PasswordField } from '@/components/common/form-field'
import { safeNextPath } from '@/features/auth/guards'
import { ApiError, errorMessage } from '@/lib/api-client'
import { isMfaChallenge } from '@/types/api'

function SecondStep({ challenge, onRestart, onDone }: { challenge: string; onRestart: () => void; onDone: () => void }) {
  const verify = useVerifyMfa()
  const [code, setCode] = useState('')
  const [recovery, setRecovery] = useState(false)
  const expired = verify.error instanceof ApiError && ['mfa_expired', 'invalid_mfa_challenge'].includes(verify.error.code)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    verify.mutate({ challenge, code: code.trim() }, { onSuccess: onDone })
  }

  return (
    <AuthLayout
      title="Two-step verification"
      description={recovery ? 'Enter one of the recovery codes you saved when you set this up.' : 'Enter the 6-digit code from your authenticator app.'}
      footer={
        <button type="button" onClick={onRestart} className="font-medium text-primary hover:underline">
          Use a different account
        </button>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {verify.error && (
          <FormAlert>
            {expired ? 'This sign-in took too long. Start again with your password.' : errorMessage(verify.error)}
          </FormAlert>
        )}
        <FormField
          key={recovery ? 'recovery' : 'totp'}
          label={recovery ? 'Recovery code' : 'Authentication code'}
          autoComplete="one-time-code"
          inputMode={recovery ? 'text' : 'numeric'}
          pattern={recovery ? undefined : '[0-9]*'}
          maxLength={recovery ? 20 : 6}
          placeholder={recovery ? 'xxxx-xxxx' : '123456'}
          value={code}
          onChange={(e) => setCode(recovery ? e.target.value : e.target.value.replace(/\D/g, ''))}
          required
        />
        {expired ? (
          <Button type="button" className="w-full" size="lg" onClick={onRestart}>
            Sign in again
          </Button>
        ) : (
          <Button type="submit" className="w-full" size="lg" loading={verify.isPending} disabled={recovery ? code.trim().length < 8 : code.length !== 6}>
            <ShieldCheck /> Verify
          </Button>
        )}
        <button
          type="button"
          className="w-full text-center text-[13px] font-medium text-primary hover:underline"
          onClick={() => {
            setRecovery(!recovery)
            setCode('')
            verify.reset()
          }}
        >
          {recovery ? 'Use your authenticator app instead' : "Can't use your app? Use a recovery code"}
        </button>
      </form>
    </AuthLayout>
  )
}

export function LoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [challenge, setChallenge] = useState<string | null>(null)

  const fieldErrors = login.error instanceof ApiError ? login.error.fieldErrors : {}
  const formError = login.error && !Object.keys(fieldErrors).length ? errorMessage(login.error) : null
  const done = () => navigate(safeNextPath(params.get('next')), { replace: true })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    login.mutate(
      { email, password },
      {
        onSuccess: (result) => {
          if (isMfaChallenge(result)) {
            setChallenge(result.challenge)
            setPassword('')
          } else done()
        },
      },
    )
  }

  if (challenge) {
    return (
      <SecondStep
        challenge={challenge}
        onDone={done}
        onRestart={() => {
          setChallenge(null)
          login.reset()
        }}
      />
    )
  }

  return (
    <AuthLayout
      title="Welcome back"
      description="Sign in to your WorkPulse workspace."
      footer={
        <>
          New to WorkPulse?{' '}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Create a workspace
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {formError && <FormAlert>{formError}</FormAlert>}
        <FormField
          label="Work email"
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          required
        />
        <PasswordField
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          required
          labelAction={
            <Link to="/forgot-password" className="text-[12px] font-medium text-primary hover:underline">
              Forgot password?
            </Link>
          }
        />
        <Button type="submit" className="w-full" size="lg" loading={login.isPending} disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}

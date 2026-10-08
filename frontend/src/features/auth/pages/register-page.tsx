import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioCard, RadioGroup } from '@/components/ui/radio-group'
import { useRegister } from '@/features/auth/api'
import { AuthLayout } from '@/features/auth/components/auth-layout'
import { FormAlert, FormField, PasswordField } from '@/components/common/form-field'
import { passwordIssues, PasswordStrength } from '@/components/common/password-strength'
import { ApiError, errorMessage } from '@/lib/api-client'

const SIZES = ['1-10', '11-50', '51-200', '201-1000', '1000+'] as const

function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export function RegisterPage() {
  const navigate = useNavigate()
  const register = useRegister()
  const [timezone] = useState(detectTimezone)
  const [form, setForm] = useState({ company_name: '', full_name: '', email: '', password: '' })
  const [size, setSize] = useState<(typeof SIZES)[number] | null>(null)
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({})

  const serverErrors = register.error instanceof ApiError ? register.error.fieldErrors : {}
  const errors = { ...serverErrors, ...clientErrors }
  const formError =
    register.error && !Object.keys(serverErrors).length ? errorMessage(register.error) : null

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) => {
    setForm((f) => ({ ...f, [key]: event.target.value }))
    setClientErrors((e) => ({ ...e, [key]: '' }))
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const issues: Record<string, string> = {}
    if (form.company_name.trim().length < 2) issues.company_name = 'Enter your company name.'
    if (form.full_name.trim().length < 2) issues.full_name = 'Enter your full name.'
    const passwordIssue = passwordIssues(form.password)
    if (passwordIssue) issues.password = passwordIssue
    setClientErrors(issues)
    if (Object.values(issues).some(Boolean)) return

    register.mutate(
      { ...form, company_size: size, timezone },
      {
        onSuccess: (session) => {
          toast.success(`Welcome to WorkPulse, ${session.user.full_name.split(' ')[0]}`, {
            description: 'Your workspace is ready. Check your inbox to verify your email.',
          })
          navigate('/dashboard', { replace: true })
        },
      },
    )
  }

  return (
    <AuthLayout
      title="Create your workspace"
      description="Start a 14-day trial. No credit card required."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {formError && <FormAlert>{formError}</FormAlert>}
        <FormField
          label="Company name"
          autoComplete="organization"
          placeholder="Acme Inc."
          value={form.company_name}
          onChange={update('company_name')}
          error={errors.company_name}
        />
        <div className="space-y-1.5">
          <Label id="company-size-label">Company size</Label>
          <RadioGroup
            aria-labelledby="company-size-label"
            className="grid-cols-5 gap-1.5"
            value={size ?? ''}
            onValueChange={(value) => setSize(value as (typeof SIZES)[number])}
          >
            {SIZES.map((option) => (
              <RadioCard
                key={option}
                value={option}
                className="h-8 text-[12px] font-medium data-[state=checked]:bg-primary-soft data-[state=checked]:text-primary-soft-foreground data-[state=checked]:ring-0"
              >
                {option}
              </RadioCard>
            ))}
          </RadioGroup>
        </div>
        <FormField
          label="Your full name"
          autoComplete="name"
          placeholder="Jane Cooper"
          value={form.full_name}
          onChange={update('full_name')}
          error={errors.full_name}
        />
        <FormField
          label="Work email"
          type="email"
          autoComplete="email"
          placeholder="jane@acme.com"
          value={form.email}
          onChange={update('email')}
          error={errors.email}
        />
        <PasswordField
          label="Password"
          autoComplete="new-password"
          value={form.password}
          onChange={update('password')}
          error={errors.password}
          hint={<PasswordStrength password={form.password} />}
        />
        <Button type="submit" className="w-full" size="lg" loading={register.isPending}>
          Create workspace
        </Button>
        <p className="text-center text-[12px] text-muted-foreground">
          Workspace timezone: <span className="font-medium text-foreground">{timezone}</span>
        </p>
      </form>
    </AuthLayout>
  )
}

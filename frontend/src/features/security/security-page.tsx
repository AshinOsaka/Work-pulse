import { useState, type FormEvent } from 'react'
import { KeyRound, MonitorSmartphone, ScrollText, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/common/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useChangePassword } from '@/features/auth/api'
import { AuditLog } from '@/features/security/audit-log'
import { SessionsCard } from '@/features/security/sessions-card'
import { TwoStepCard } from '@/features/security/two-step-card'
import { FormAlert, PasswordField } from '@/components/common/form-field'
import { passwordIssues, PasswordStrength } from '@/components/common/password-strength'
import { ApiError, errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'

function PasswordTab() {
  const change = useChangePassword()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const serverErrors = change.error instanceof ApiError ? change.error.fieldErrors : {}

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const issues: Record<string, string> = {}
    const issue = passwordIssues(form.next)
    if (issue) issues.next = issue
    if (form.next !== form.confirm) issues.confirm = 'Passwords do not match.'
    setErrors(issues)
    if (Object.keys(issues).length) return
    change.mutate(
      { current_password: form.current, new_password: form.next },
      {
        onSuccess: () => {
          setForm({ current: '', next: '', confirm: '' })
          toast.success('Password updated', { description: 'All other sessions have been signed out.' })
        },
      },
    )
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <form onSubmit={onSubmit} noValidate>
          <CardHeader>
            <CardTitle>Change password</CardTitle>
            <CardDescription>Updating your password signs you out on all other devices.</CardDescription>
          </CardHeader>
          <CardContent className="max-w-md space-y-4">
            {change.error && !Object.keys(serverErrors).length && <FormAlert>{errorMessage(change.error)}</FormAlert>}
            <PasswordField
              label="Current password"
              autoComplete="current-password"
              value={form.current}
              onChange={(e) => setForm({ ...form, current: e.target.value })}
            />
            <PasswordField
              label="New password"
              autoComplete="new-password"
              value={form.next}
              onChange={(e) => setForm({ ...form, next: e.target.value })}
              error={errors.next ?? serverErrors.new_password}
              hint={<PasswordStrength password={form.next} />}
            />
            <PasswordField
              label="Confirm new password"
              autoComplete="new-password"
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              error={errors.confirm}
            />
          </CardContent>
          <CardFooter className="justify-end">
            <Button type="submit" size="sm" loading={change.isPending} disabled={!form.current || !form.next}>
              Update password
            </Button>
          </CardFooter>
        </form>
      </Card>
      <TwoStepCard />
    </div>
  )
}

export default function SecurityPage() {
  const { can } = usePermissions()
  return (
    <div className="space-y-6">
      <PageHeader title="Security" description="Protect your account and control access to your workspace." icon={ShieldCheck} />
      <Tabs defaultValue="password">
        <TabsList>
          <TabsTrigger value="password">
            <KeyRound /> Password & 2-step
          </TabsTrigger>
          <TabsTrigger value="sessions">
            <MonitorSmartphone /> Sessions
          </TabsTrigger>
          {can('AUDIT_LOG_VIEW') && (
            <TabsTrigger value="audit">
              <ScrollText /> Audit log
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="password">
          <PasswordTab />
        </TabsContent>
        <TabsContent value="sessions">
          <SessionsCard />
        </TabsContent>
        {can('AUDIT_LOG_VIEW') && (
          <TabsContent value="audit">
            <AuditLog />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}

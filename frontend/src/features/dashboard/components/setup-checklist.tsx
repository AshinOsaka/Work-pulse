import { useQuery } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/misc'
import { useResendVerification } from '@/features/auth/api'
import { useDepartments, usePeopleSummary } from '@/features/people/api'
import { api, errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import { useUiStore } from '@/stores/ui-store'

interface Step {
  title: string
  done: boolean
  action?: React.ReactNode
}

/** Compact onboarding strip shown above the dashboard until the workspace is set up. */
export function SetupChecklist() {
  const user = useAuthStore((s) => s.user)
  const { can } = usePermissions()
  const dismissed = useUiStore((s) => s.checklistDismissed)
  const setDismissed = useUiStore((s) => s.setChecklistDismissed)
  const resend = useResendVerification()
  const summary = usePeopleSummary()
  // Any employee with a registered agent device means the agent has been rolled out.
  const agentInstalled = useQuery({
    queryKey: ['setup', 'agent-installed'],
    queryFn: async () => (await api.get<{ employees: { device: unknown }[] }>('/presence')).employees.some((e) => e.device),
    enabled: can('ACTIVITY_VIEW'),
    staleTime: 60_000,
  })
  const departments = useDepartments(can('EMPLOYEE_VIEW'))
  if (!user || dismissed || !can('EMPLOYEE_MANAGE') || summary.isPending || departments.isPending) return null

  const steps: Step[] = [
    { title: 'Create your workspace', done: true },
    {
      title: 'Verify your email',
      done: user.email_verified,
      action: (
        <Button
          size="sm"
          variant="link"
          className="h-auto p-0 text-[12px]"
          disabled={resend.isPending}
          onClick={() =>
            resend.mutate(undefined, {
              onSuccess: (r) => toast.success(r.message),
              onError: (e) => toast.error(errorMessage(e)),
            })
          }
        >
          Resend link
        </Button>
      ),
    },
    {
      title: 'Set up departments',
      done: Boolean(departments.data?.length),
      action: (
        <Link to="/people/departments" className="text-[12px] font-medium text-primary hover:underline">
          Set up
        </Link>
      ),
    },
    {
      title: 'Add your team',
      done: Boolean(summary.data && summary.data.total > 1),
      action: (
        <Link to="/people/employees" className="text-[12px] font-medium text-primary hover:underline">
          Add people
        </Link>
      ),
    },
    {
      title: 'Install the desktop agent',
      done: Boolean(agentInstalled.data),
      action: <span className="text-[12px] text-muted-foreground">Employees sign in from the agent</span>,
    },
  ]
  const completed = steps.filter((s) => s.done).length
  if (completed === steps.length) return null

  return (
    <Card className="relative p-4 animate-in duration-300 fade-in-0">
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="absolute top-3 right-3 rounded p-1 text-muted-foreground transition hover:bg-accent hover:text-foreground"
        aria-label="Dismiss setup checklist"
      >
        <X className="size-4" />
      </button>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="lg:w-56 lg:shrink-0">
          <p className="text-[13px] font-semibold">Finish setting up</p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {completed} of {steps.length} steps complete
          </p>
          <Progress value={(completed / steps.length) * 100} className="mt-2 h-1" aria-label="Setup progress" />
        </div>
        <ol className="grid flex-1 gap-2 pr-6 sm:grid-cols-2 xl:grid-cols-5">
          {steps.map((step) => (
            <li key={step.title} className={cn('flex items-start gap-2 rounded-lg border px-3 py-2', step.done ? 'bg-subtle' : 'bg-card')}>
              <span
                className={cn(
                  'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border',
                  step.done ? 'border-transparent bg-primary-solid text-primary-foreground' : 'border-dashed',
                )}
                aria-hidden
              >
                {step.done && <Check className="size-2.5" strokeWidth={3} />}
              </span>
              <div className="min-w-0">
                <p className={cn('text-[12px] font-medium', step.done && 'text-muted-foreground line-through')}>
                  {step.title}
                  <span className="sr-only">{step.done ? ' (done)' : ' (to do)'}</span>
                </p>
                {!step.done && step.action}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  )
}

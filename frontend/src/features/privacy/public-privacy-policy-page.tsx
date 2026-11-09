import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Ban, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router'

import { Logo } from '@/components/common/logo'
import { Skeleton } from '@/components/ui/misc'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { api } from '@/lib/api-client'

/** General facts from the server (same source as the in-app policy). No workspace data. */
interface PublicPrivacyFacts {
  never_collected: string[]
  detailed_activity_days: number
  raw_event_days: number
  default_screenshot_days: number
  report_file_days: number
  contact_email: string | null
}

const LAST_UPDATED = '9 November 2026'

/**
 * The public privacy policy of the WorkPulse service: readable without signing in (also the link Google needs for
 * the Gmail sender). It describes the service in general — each workspace's own settings stay on the signed-in
 * Monitoring & privacy page. Facts that the system enforces (what is never collected, retention) come from the API.
 */
export default function PublicPrivacyPolicyPage() {
  useDocumentTitle('Privacy policy')
  const facts = useQuery({
    queryKey: ['privacy', 'public'],
    queryFn: () => api.get<PublicPrivacyFacts>('/privacy/public', { auth: false }),
    staleTime: 10 * 60_000,
  })
  const f = facts.data

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <Link to="/login" aria-label="WorkPulse sign in">
            <Logo />
          </Link>
          <Link to="/login" className="text-[13px] font-medium text-primary hover:underline">
            Sign in
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-10">
        <h1 className="text-[28px] font-semibold tracking-tight">Privacy policy</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">Last updated {LAST_UPDATED}</p>

        <div className="mt-8 space-y-8 text-[14px] leading-relaxed">
          <Section title="About WorkPulse">
            <p>
              WorkPulse is a workplace time and activity tool. Organisations (“your employer”) use it to see work time,
              attendance and how working time is spent. Each organisation decides which features are switched on.
              Employees review what may be recorded and accept it when they first sign in to the WorkPulse desktop
              agent, and the agent stays visible in the system tray while it runs.
            </p>
            <p className="mt-3">
              Your employer controls the data recorded about its staff. WorkPulse stores and processes it on the
              employer’s behalf to provide the service. Signed-in employees can see exactly what their own workspace
              records on its <strong>Monitoring &amp; privacy</strong> page.
            </p>
          </Section>

          <Section title="What we collect">
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                <strong>Account details</strong> your employer adds: name, work email, job title, department, team and
                manager.
              </li>
              <li>
                <strong>Work time</strong>: when work sessions start and stop, and active versus idle time.
              </li>
              <li>
                <strong>Applications</strong> used and for how long; window titles only if your employer turns this on
                (never for password managers, private browsing, messaging or e-mail).
              </li>
              <li>
                <strong>Websites</strong>: the site’s domain only (e.g. github.com), and only if your employer turns
                this on.
              </li>
              <li>
                <strong>Keyboard and mouse activity counts</strong>, if switched on: how many, never which keys or what
                was typed.
              </li>
              <li>
                <strong>Screenshots</strong>, if switched on: taken during an active work session only.
              </li>
              <li>
                <strong>Live screen view</strong>, if switched on: streamed to the person who asked; the video is not
                recorded.
              </li>
              <li>
                <strong>Projects, tasks and time</strong> people add themselves.
              </li>
              <li>
                <strong>Device and security records</strong>: the computer’s name and operating system, sign-ins, and an
                audit trail of administrative actions.
              </li>
            </ul>
          </Section>

          <Section title="What we never collect" icon={<Ban className="size-4 text-cat-productive" aria-hidden />}>
            {f ? (
              <ul className="space-y-1.5">
                {f.never_collected.map((item) => (
                  <li key={item} className="flex gap-2">
                    <ShieldCheck className="mt-1 size-3.5 shrink-0 text-cat-productive" aria-hidden />
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <FactsFallback loading={facts.isPending} />
            )}
          </Section>

          <Section title="How we use it">
            <p>
              Only to provide the service to your employer: attendance and work-time records, activity and productivity
              summaries, reports, security, and service e-mails such as invitations and password resets. We do not sell
              data, use it for advertising, or share it with third parties except the providers that host and run the
              service.
            </p>
          </Section>

          <Section title="Google user data (Gmail API)">
            <p>
              WorkPulse uses the Gmail API only to <strong>send</strong> service e-mails (invitations, password resets
              and similar) from WorkPulse’s own Gmail account. It does not read, store or share anyone’s Gmail messages
              or other Google user data. Our use of information received from Google APIs adheres to the{' '}
              <a
                className="text-primary hover:underline"
                href="https://developers.google.com/terms/api-services-user-data-policy"
                target="_blank"
                rel="noreferrer"
              >
                Google API Services User Data Policy
              </a>
              , including the Limited Use requirements.
            </p>
          </Section>

          <Section title="Who can see it">
            <p>
              Within your organisation: its administrators, and managers or team leads for the people they are
              responsible for. Each person can see their own data. Access is controlled by roles and checked by the
              server on every request.
            </p>
          </Section>

          <Section title="How long we keep it">
            {f ? (
              <ul className="list-disc space-y-1.5 pl-5">
                <li>Detailed activity: {f.detailed_activity_days} days. Daily totals: while the workspace exists.</li>
                <li>Raw events from the desktop agent: {f.raw_event_days} days.</li>
                <li>Screenshots: deleted automatically after the period your employer sets ({f.default_screenshot_days} days by default).</li>
                <li>Generated report files: {f.report_file_days} days.</li>
                <li>Other records: while the workspace exists, or until an administrator deletes them.</li>
              </ul>
            ) : (
              <FactsFallback loading={facts.isPending} />
            )}
          </Section>

          <Section title="Security">
            <p>
              Data is sent over encrypted connections (HTTPS) and hosted with Render and MongoDB Atlas. Passwords are
              stored only as secure hashes, two-step verification is available, and live views and administrative
              changes are recorded in an audit trail.
            </p>
          </Section>

          <Section title="Your choices">
            <p>
              Employees can ask their employer which features are on, or to correct or delete their data. Employers can
              change what is recorded at any time and delete records or their whole workspace.
            </p>
          </Section>

          <Section title="Contact">
            <p>
              Questions about this policy:{' '}
              {f?.contact_email ? (
                <a className="text-primary hover:underline" href={`mailto:${f.contact_email}`}>
                  {f.contact_email}
                </a>
              ) : (
                'please contact your employer’s WorkPulse administrator.'
              )}
            </p>
          </Section>
        </div>
      </main>
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 flex items-center gap-2 text-[17px] font-semibold">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  )
}

function FactsFallback({ loading }: { loading: boolean }) {
  return loading ? (
    <div className="space-y-2">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  ) : (
    <p className="text-muted-foreground">This part couldn’t be loaded right now. Please refresh the page.</p>
  )
}

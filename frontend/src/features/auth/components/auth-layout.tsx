import type { ReactNode } from 'react'
import { Fingerprint, LineChart, ShieldCheck } from 'lucide-react'

import { Logo } from '@/components/common/logo'
import { useDocumentTitle } from '@/hooks/use-document-title'

const CURRENT_YEAR = new Date().getFullYear()

const PRINCIPLES = [
  {
    icon: LineChart,
    title: 'Clarity over surveillance',
    body: 'Understand how work actually happens across teams, with insight focused on patterns rather than people.',
  },
  {
    icon: ShieldCheck,
    title: 'Policy-driven by design',
    body: 'Every capability is governed by roles, permissions and workspace policies, with a complete audit trail.',
  },
  {
    icon: Fingerprint,
    title: 'Built for trust',
    body: 'Tenant-isolated data, rotating sessions and secure-by-default infrastructure from day one.',
  },
]

interface AuthLayoutProps {
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

export function AuthLayout({ title, description, children, footer }: AuthLayoutProps) {
  useDocumentTitle(title)
  return (
    <div className="grid min-h-svh bg-background lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex flex-col px-6 py-8 sm:px-10">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[380px] animate-in duration-500 fade-in-0 slide-in-from-bottom-2">
            <div className="mb-7 space-y-1.5">
              <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
              {description && <p className="text-sm text-muted-foreground">{description}</p>}
            </div>
            {children}
            {footer && <div className="mt-7 text-center text-[13px] text-muted-foreground">{footer}</div>}
          </div>
        </div>
        <p className="text-[12px] text-muted-foreground">© {CURRENT_YEAR} WorkPulse</p>
      </div>

      <aside className="relative hidden overflow-hidden bg-[oklch(0.24_0.09_278)] p-3 lg:block">
        <div className="relative flex h-full flex-col justify-between overflow-hidden rounded-2xl bg-gradient-to-br from-[oklch(0.42_0.2_277)] via-[oklch(0.33_0.16_280)] to-[oklch(0.22_0.08_285)] p-12 text-white">
          <div className="pointer-events-none absolute inset-0 bg-dot-grid text-white/40 [mask-image:radial-gradient(ellipse_at_top_right,black,transparent_70%)]" />
          <div className="pointer-events-none absolute -top-32 -right-32 size-[28rem] rounded-full bg-[oklch(0.65_0.2_300/0.35)] blur-3xl" />
          <div className="pointer-events-none absolute -bottom-40 -left-24 size-[26rem] rounded-full bg-[oklch(0.6_0.18_260/0.3)] blur-3xl" />

          <div className="relative">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[12px] font-medium backdrop-blur">
              Workforce intelligence platform
            </p>
            <h2 className="mt-6 max-w-md text-[34px] leading-[1.15] font-semibold tracking-tight text-balance">
              See how your organisation really works.
            </h2>
            <p className="mt-4 max-w-md text-[15px] text-white/70">
              WorkPulse brings time, activity and productivity signals together, so leaders can make better decisions.
            </p>
          </div>

          <ul className="relative grid gap-3">
            {PRINCIPLES.map(({ icon: Icon, title: heading, body }) => (
              <li key={heading} className="flex gap-4 rounded-xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="size-4.5" />
                </div>
                <div>
                  <p className="text-sm font-medium">{heading}</p>
                  <p className="mt-0.5 text-[13px] text-white/65">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  )
}

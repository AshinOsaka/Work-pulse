import type { ReactNode } from 'react'
import { TrendingUp } from 'lucide-react'

import { Logo } from '@/components/common/logo'
import { useDocumentTitle } from '@/hooks/use-document-title'

const CURRENT_YEAR = new Date().getFullYear()

interface AuthLayoutProps {
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

/**
 * Premium two-column auth shell. The whole login is rendered dark (scoped `.dark`, so the shared form
 * components pick up the dark tokens without any global theme change). Left: a minimal sign-in form.
 * Right: a continuous, lightweight productivity-growth animation (inline SVG + CSS, no new dependency).
 * This is purely visual — every form, handler and route is untouched.
 */
export function AuthLayout({ title, description, children, footer }: AuthLayoutProps) {
  useDocumentTitle(title)
  return (
    <div className="auth-shell dark relative grid min-h-svh overflow-hidden bg-[#070712] text-foreground lg:grid-cols-[minmax(0,1fr)_minmax(0,1.04fr)]">
      <AuthStyles />

      {/* Ambient background glow, shared by both columns so they read as one surface. */}
      <div aria-hidden className="pointer-events-none absolute -top-40 -left-32 size-[34rem] rounded-full bg-[radial-gradient(circle,rgba(124,58,237,0.22),transparent_70%)] blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-48 left-1/4 size-[32rem] rounded-full bg-[radial-gradient(circle,rgba(56,135,229,0.16),transparent_70%)] blur-3xl" />

      {/* Left — the sign-in form */}
      <div className="relative z-10 flex min-h-svh flex-col px-6 py-8 sm:px-10 lg:px-14">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[400px] duration-700 animate-in fade-in-0 slide-in-from-bottom-3">
            <div className="mb-8 space-y-2">
              <h1 className="text-[28px] leading-tight font-semibold tracking-tight">{title}</h1>
              {description && <p className="text-sm text-muted-foreground">{description}</p>}
            </div>
            {children}
            {footer && <div className="mt-8 text-center text-[13px] text-muted-foreground">{footer}</div>}
          </div>
        </div>
        <p className="text-[12px] text-muted-foreground">© {CURRENT_YEAR} WorkPulse</p>
      </div>

      {/* Right — heading + animated productivity-growth visualization */}
      <aside className="relative hidden overflow-hidden p-3 lg:block">
        <div className="relative flex h-full flex-col overflow-hidden rounded-[1.75rem] border border-white/10 bg-gradient-to-br from-[#17102f] via-[#110b27] to-[#0a0a1c]">
          <div aria-hidden className="pointer-events-none absolute -top-24 -right-16 size-[26rem] rounded-full bg-[radial-gradient(circle,rgba(167,139,250,0.3),transparent_70%)] blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute -bottom-28 -left-16 size-[24rem] rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.2),transparent_70%)] blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-dot-grid text-white/[0.04] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />

          <div className="relative z-10 flex h-full flex-col justify-between p-12">
            <div className="max-w-sm">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1 text-[12px] font-medium text-white/80 backdrop-blur">
                Workforce intelligence
              </span>
              <h2 className="mt-6 text-[32px] leading-[1.1] font-semibold tracking-tight text-balance text-white">
                See your team&apos;s productivity rise.
              </h2>
              <p className="mt-3 text-[14px] text-white/60">
                Real-time activity, focus and customer time — in one clear view.
              </p>
            </div>
            <div className="flex flex-1 items-center justify-center pt-6">
              <ProductivityViz />
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}

/** The continuous productivity-growth visual: a rising glowing line, moving data points, growing bars
 *  and a live-feeling score. Decorative only (aria-hidden). */
function ProductivityViz() {
  const line = 'M40,300 C110,292 148,222 210,236 C272,250 306,150 368,140 C418,132 470,92 500,70'
  const area = `${line} L500,340 L40,340 Z`
  const points = [
    { x: 210, y: 236 },
    { x: 368, y: 140 },
    { x: 500, y: 70 },
  ]
  const bars = [60, 132, 204, 276, 348, 420].map((x, i) => ({ x, h: 36 + i * 24 }))
  return (
    <div aria-hidden className="relative w-full max-w-[460px] px-8">
      {/* Floating score badge */}
      <div className="viz-float absolute -top-2 right-6 z-10 flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 backdrop-blur-md">
        <span className="flex size-8 items-center justify-center rounded-xl bg-[linear-gradient(135deg,#7c3aed,#6366f1)] text-white shadow-[0_6px_20px_-6px_rgba(124,58,237,0.9)]">
          <TrendingUp className="size-4" />
        </span>
        <div className="leading-none">
          <p className="viz-score text-[22px] font-semibold tracking-tight text-white tabular">98%</p>
          <p className="mt-0.5 text-[11px] font-medium text-emerald-400">▲ 24%</p>
        </div>
      </div>

      <svg viewBox="0 0 540 360" className="h-auto w-full" role="presentation">
        <defs>
          <linearGradient id="viz-line" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#6d28d9" />
            <stop offset="55%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#38bdf8" />
          </linearGradient>
          <linearGradient id="viz-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="viz-bar" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="#6d28d9" stopOpacity="0.1" />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity="0.45" />
          </linearGradient>
          <filter id="viz-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Faint grid */}
        {[90, 160, 230, 300].map((y) => (
          <line key={y} x1="30" y1={y} x2="510" y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
        ))}

        {/* Growing bars */}
        {bars.map((b, i) => (
          <rect
            key={b.x}
            className="viz-bar-rect"
            x={b.x}
            y={340 - b.h}
            width="26"
            height={b.h}
            rx="6"
            fill="url(#viz-bar)"
            style={{ animationDelay: `${0.3 + i * 0.12}s` }}
          />
        ))}

        {/* Area + rising line */}
        <path className="viz-area-path" d={area} fill="url(#viz-area)" />
        <path
          className="viz-line-path"
          d={line}
          fill="none"
          stroke="url(#viz-line)"
          strokeWidth="3.5"
          strokeLinecap="round"
          filter="url(#viz-glow)"
          pathLength={1000}
        />

        {/* Pulsing data points */}
        {points.map((p, i) => (
          <circle key={`${p.x}-${p.y}`} className="viz-point" cx={p.x} cy={p.y} r="5.5" fill="#fff" filter="url(#viz-glow)" style={{ animationDelay: `${1.6 + i * 0.2}s` }}>
            <animate attributeName="opacity" values="0.55;1;0.55" dur="2.4s" begin={`${2 + i * 0.2}s`} repeatCount="indefinite" />
          </circle>
        ))}

        {/* Glowing dot travelling along the line */}
        <circle r="6.5" fill="#ffffff" filter="url(#viz-glow)">
          <animateMotion dur="5s" repeatCount="indefinite" calcMode="linear" keyPoints="0;1" keyTimes="0;1" path={line} />
          <animate attributeName="opacity" values="0;1;1;0" dur="5s" repeatCount="indefinite" />
        </circle>
      </svg>
    </div>
  )
}

/** Scoped styles + animations for the login (kept here so no other module changes). */
function AuthStyles() {
  return (
    <style>{`
      /* Premium display font for headings, brand and the score (loaded in index.html). */
      .auth-shell h1,
      .auth-shell h2,
      .auth-shell .auth-brand,
      .auth-shell .viz-score {
        font-family: 'Sora', 'Inter Variable', ui-sans-serif, system-ui, sans-serif;
        letter-spacing: -0.02em;
      }

      .auth-shell form button[type="submit"]:not(:disabled) {
        background-image: linear-gradient(to right, #7c3aed, #6366f1);
        box-shadow: 0 10px 30px -10px rgba(124,58,237,0.7);
        transition: filter .2s ease, box-shadow .2s ease, transform .08s ease;
      }
      .auth-shell form button[type="submit"]:not(:disabled):hover {
        filter: brightness(1.08) saturate(1.05);
        box-shadow: 0 14px 36px -8px rgba(124,58,237,0.85);
      }
      .auth-shell form button[type="submit"]:not(:disabled):active { transform: translateY(1px); }

      @keyframes viz-draw { to { stroke-dashoffset: 0; } }
      @keyframes viz-fade { to { opacity: 1; } }
      @keyframes viz-pop { 0% { transform: scale(0); opacity: 0; } 60% { opacity: 1; } 100% { transform: scale(1); opacity: 1; } }
      @keyframes viz-grow { to { transform: scaleY(1); } }
      @keyframes viz-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-9px); } }

      @media (prefers-reduced-motion: no-preference) {
        .viz-line-path { stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: viz-draw 2.6s cubic-bezier(.22,1,.36,1) forwards; }
        .viz-area-path { opacity: 0; animation: viz-fade 1.2s ease-out .9s forwards; }
        .viz-point { transform-box: fill-box; transform-origin: center; transform: scale(0); animation: viz-pop .5s cubic-bezier(.22,1,.36,1) forwards; }
        .viz-bar-rect { transform-box: fill-box; transform-origin: bottom; transform: scaleY(0); animation: viz-grow 1s cubic-bezier(.22,1,.36,1) forwards; }
        .viz-float { animation: viz-float 6s ease-in-out infinite; }
      }
    `}</style>
  )
}

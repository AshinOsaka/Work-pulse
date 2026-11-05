import { useState, type ReactNode } from 'react'
import { CheckCircle2, Download, Monitor, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAgentRelease } from '@/features/settings/api'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/stores/auth-store'

/** The four-pane Windows mark, drawn in Windows blue. */
function WindowsLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 88 88" className={className} aria-hidden>
      <path fill="#0078D4" d="M0 12.4 35.7 7.5v34.5H0zM40 6.9 87.3 0v41.6H40zM0 45.7h35.7v34.6L0 75.4zM40 46.2h47.3V88L40 81.2z" />
    </svg>
  )
}

/** The Apple mark (simple-icons path, CC0), in the text colour so it suits light and dark mode. */
function AppleLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn('fill-foreground', className)} aria-hidden>
      <path d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701" />
    </svg>
  )
}

/** A simple Linux penguin (Tux style): black body, white belly and face, orange beak and feet. */
function LinuxLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 72" className={className} aria-hidden>
      {/* feet */}
      <ellipse cx="19" cy="64" rx="11" ry="5.5" fill="#F5A623" />
      <ellipse cx="45" cy="64" rx="11" ry="5.5" fill="#F5A623" />
      {/* body and head */}
      <ellipse cx="32" cy="42" rx="20" ry="23" fill="#1B1B1F" />
      <ellipse cx="32" cy="17" rx="13" ry="14" fill="#1B1B1F" />
      {/* belly and face */}
      <ellipse cx="32" cy="45" rx="13.5" ry="17" fill="#FFFFFF" />
      <ellipse cx="32" cy="20" rx="8.5" ry="8" fill="#FFFFFF" />
      {/* eyes */}
      <ellipse cx="28" cy="15.5" rx="2.6" ry="3.2" fill="#FFFFFF" />
      <ellipse cx="36" cy="15.5" rx="2.6" ry="3.2" fill="#FFFFFF" />
      <circle cx="28.6" cy="16.2" r="1.5" fill="#1B1B1F" />
      <circle cx="35.4" cy="16.2" r="1.5" fill="#1B1B1F" />
      {/* beak */}
      <path d="M26 21.5c2-1.6 10-1.6 12 0-1.5 3.2-4 4.6-6 4.6s-4.5-1.4-6-4.6z" fill="#F5A623" />
      {/* flippers */}
      <path d="M12.5 36c-4 6-5 15-2 20 2.5-2 4-8 4.5-14z" fill="#1B1B1F" />
      <path d="M51.5 36c4 6 5 15 2 20-2.5-2-4-8-4.5-14z" fill="#1B1B1F" />
    </svg>
  )
}

type Phase = { state: 'idle' } | { state: 'downloading'; percent: number | null } | { state: 'done' }

/** The installer's file name from its link, e.g. WorkPulseAgentSetup-0.8.1.exe. */
function fileName(url: string, version: string): string {
  try {
    const last = decodeURIComponent(new URL(url, window.location.href).pathname.split('/').pop() ?? '')
    if (last) return last
  } catch {
    /* fall through */
  }
  return `WorkPulseAgentSetup-${version}.exe`
}

/**
 * Downloads with progress so we can say when it has finished. If the file's host doesn't allow that (no CORS),
 * the browser downloads it the normal way and we say it has started instead.
 */
async function downloadWithProgress(url: string, name: string, onProgress: (percent: number | null) => void): Promise<'complete' | 'started'> {
  try {
    const response = await fetch(url)
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
    const total = Number(response.headers.get('content-length')) || 0
    const reader = response.body.getReader()
    const chunks: Uint8Array[] = []
    let received = 0
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
      received += value.length
      onProgress(total ? Math.min(99, Math.round((100 * received) / total)) : null)
    }
    const href = URL.createObjectURL(new Blob(chunks as BlobPart[], { type: 'application/octet-stream' }))
    const a = Object.assign(document.createElement('a'), { href, download: name })
    document.body.append(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(href), 60_000)
    return 'complete'
  } catch {
    const a = Object.assign(document.createElement('a'), { href: url, download: name, rel: 'noopener' })
    document.body.append(a)
    a.click()
    a.remove()
    return 'started'
  }
}

function PlatformCard({
  logo,
  name,
  children,
  soon,
}: {
  logo: ReactNode
  name: string
  children: ReactNode
  soon?: boolean
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-4 rounded-2xl border p-5 text-center transition-colors',
        soon ? 'bg-muted/40' : 'border-[#0078D4]/25 bg-gradient-to-b from-[#0078D4]/[0.07] to-card shadow-xs',
      )}
    >
      <div className={cn('flex h-20 items-center justify-center', soon && 'opacity-60')}>{logo}</div>
      <p className={cn('text-[13px] font-semibold', soon && 'text-muted-foreground')}>{name}</p>
      <div className="w-full">{children}</div>
    </div>
  )
}

/** Top-bar "Download agent" button and its pop-up with the current desktop agent. */
export function AgentDownloadButton() {
  const [open, setOpen] = useState(false)
  const [phase, setPhase] = useState<Phase>({ state: 'idle' })
  const release = useAgentRelease()
  const { can } = usePermissions()
  const url = release.data?.download_url
  const version = release.data?.version ?? ''

  const start = async () => {
    if (!url || phase.state === 'downloading') return
    setPhase({ state: 'downloading', percent: 0 })
    const name = fileName(url, version)
    const result = await downloadWithProgress(url, name, (percent) => setPhase({ state: 'downloading', percent }))
    setPhase({ state: 'done' })
    if (result === 'complete') {
      toast.success('Download complete', { description: `Open ${name} from your Downloads folder to install the agent.` })
    } else {
      toast.success('Download started', { description: `${name} is saving to your Downloads folder.` })
    }
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-foreground" onClick={() => setOpen(true)} aria-label="Download agent">
            <Download />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Download agent</TooltipContent>
      </Tooltip>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next && phase.state === 'done') setPhase({ state: 'idle' })
        }}
      >
        <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-xl" showCloseButton={false}>
          {/* Colour band header */}
          <div className="relative bg-gradient-to-br from-primary-solid to-[oklch(0.5_0.2_300)] px-6 py-5 text-white">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="absolute top-4 right-4 rounded-md p-1 text-white/80 transition hover:bg-white/15 hover:text-white focus-visible:ring-[3px] focus-visible:ring-white/50 focus-visible:outline-none"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
            <div className="flex items-center gap-3 pr-8">
              <span className="flex size-10 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25" aria-hidden>
                <Monitor className="size-5" />
              </span>
              <div>
                <DialogTitle className="text-[17px] text-white">Desktop agent</DialogTitle>
                <DialogDescription className="text-white/80">
                  WorkPulse for Windows{version && ` · version ${version}`}
                </DialogDescription>
              </div>
            </div>
          </div>

          <div className="grid gap-3 p-6 sm:grid-cols-3">
            <PlatformCard logo={<WindowsLogo className="size-16" />} name="Windows">
              {url ? (
                <Button
                  className="w-full bg-foreground text-background hover:bg-foreground/90"
                  onClick={() => void start()}
                  loading={phase.state === 'downloading'}
                  aria-live="polite"
                >
                  {phase.state === 'downloading' ? (
                    phase.percent !== null ? `${phase.percent}%` : 'Downloading…'
                  ) : phase.state === 'done' ? (
                    <>
                      <CheckCircle2 /> Downloaded
                    </>
                  ) : (
                    <>
                      <Download /> Windows
                    </>
                  )}
                </Button>
              ) : (
                <p className="text-[11.5px] text-muted-foreground">
                  Not published yet.
                  {can('POLICY_MANAGE') && (
                    <>
                      {' '}
                      Set <code>AGENT_DOWNLOAD_URL</code> on the server.
                    </>
                  )}
                </p>
              )}
            </PlatformCard>
            <PlatformCard logo={<AppleLogo className="size-14" />} name="Mac" soon>
              <span className="inline-block rounded-full bg-muted px-3 py-1 text-[11.5px] font-medium text-muted-foreground">Coming soon</span>
            </PlatformCard>
            <PlatformCard logo={<LinuxLogo className="h-16 w-14" />} name="Linux" soon>
              <span className="inline-block rounded-full bg-muted px-3 py-1 text-[11.5px] font-medium text-muted-foreground">Coming soon</span>
            </PlatformCard>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

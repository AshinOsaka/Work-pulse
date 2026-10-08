import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Clock, Maximize, Minimize, MonitorPlay, MonitorX, Play, Square, WifiOff } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/misc'
import { liveKeys, useLiveSession, useStartLive } from '@/features/live/api'
import { endReasonLabel } from '@/features/live/meta'
import { useLiveStream, type StreamPhase, type StreamStats } from '@/features/live/use-live-stream'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useNow } from '@/hooks/use-now'
import { errorMessage } from '@/lib/api-client'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const QUALITY = {
  good: { label: 'Good', bars: 3, color: 'bg-emerald-400' },
  fair: { label: 'Fair', bars: 2, color: 'bg-amber-400' },
  poor: { label: 'Poor', bars: 1, color: 'bg-red-400' },
} as const

function QualityMeter({ stats, live }: { stats: StreamStats; live: boolean }) {
  const q = live && stats.quality ? QUALITY[stats.quality] : null
  const detail = [
    stats.rttMs !== null && `${stats.rttMs} ms latency`,
    stats.lossPct !== null && `${stats.lossPct}% packet loss`,
    stats.fps !== null && `${stats.fps} fps`,
    stats.kbps !== null && `${stats.kbps} kbps`,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <div className="flex items-center gap-2" title={detail || undefined}>
      <span className="flex h-3.5 items-end gap-[2px]" aria-hidden>
        {[1, 2, 3].map((bar) => (
          <span key={bar} className={cn('w-[3px] rounded-sm', q && bar <= q.bars ? q.color : 'bg-white/20')} style={{ height: `${bar * 33}%` }} />
        ))}
      </span>
      <span className="text-[12px] text-white/80">
        <span className="sr-only">Connection quality: </span>
        {q ? q.label : '—'}
        {live && detail && <span className="sr-only">, {detail}</span>}
      </span>
    </div>
  )
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-medium tracking-wider text-white/40 uppercase">{label}</span>
      <span className="text-[13px] text-white tabular">{children}</span>
    </div>
  )
}

const PHASE_BADGE: Record<StreamPhase, { label: string; className: string; pulse?: boolean }> = {
  connecting: { label: 'Connecting', className: 'bg-white/10 text-white/80' },
  waiting: { label: 'Waiting', className: 'bg-amber-500/20 text-amber-300' },
  negotiating: { label: 'Connecting', className: 'bg-white/10 text-white/80' },
  live: { label: 'Live', className: 'bg-red-600 text-white', pulse: true },
  reconnecting: {
    label: 'Reconnecting',
    className: 'bg-amber-500/20 text-amber-300',
  },
  ended: { label: 'Ended', className: 'bg-white/10 text-white/60' },
}

/** Each session gets a fresh viewer: "Start again" navigates to a new session id. */
export default function LiveViewerPage() {
  const { sessionId } = useParams()
  return <LiveViewer key={sessionId} sessionId={sessionId} />
}

function LiveViewer({ sessionId }: { sessionId: string | undefined }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const session = useLiveSession(sessionId)
  const restart = useStartLive()
  const videoRef = useRef<HTMLVideoElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const { phase, endReason, agentOnline, networkOffline, connectedAt, endedAt, stats, stop } = useLiveStream(sessionId, videoRef)
  const [fullscreen, setFullscreen] = useState(false)
  const now = useNow(1000)
  const employee = session.data?.employee
  const name = employee?.full_name ?? 'Employee'
  const first = name.split(' ')[0]
  useDocumentTitle(phase === 'live' ? `● Live · ${name}` : `Live view · ${name}`)

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void stageRef.current?.requestFullscreen().catch(() => toast.error('Fullscreen is not available here.'))
  }, [])

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stageRef.current)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'f' && !(event.target instanceof HTMLInputElement) && !event.metaKey && !event.ctrlKey) toggleFullscreen()
    }
    document.addEventListener('fullscreenchange', onChange)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('fullscreenchange', onChange)
      window.removeEventListener('keydown', onKey)
    }
  }, [toggleFullscreen])

  // Stop Stream: the server ends the session (and tells the agent), the peer connection and socket close, and the
  // manager goes back to Live Tracking. Sessions that end any other way stay on this page with the reason.
  const [stopping, setStopping] = useState(false)
  const stopStream = () => {
    setStopping(true)
    stop()
  }
  useEffect(() => {
    if (stopping && phase === 'ended') {
      // Stopped over the signalling socket, so refresh what the list and log show before going back.
      void queryClient.invalidateQueries({ queryKey: liveKeys.all })
      toast.success(`Live stream with ${name} stopped`)
      navigate('/live', { replace: true })
    }
  }, [stopping, phase, name, navigate, queryClient])

  const startAgain = () => {
    if (!employee) return
    restart.mutate(employee.id, {
      onSuccess: (next) => navigate(`/live/${next.id}`, { replace: true }),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const live = phase === 'live'
  const badge = PHASE_BADGE[phase]
  const duration = connectedAt ? clock((endedAt ?? now) - connectedAt) : '00:00'
  const resolution = stats.width && stats.height ? `${stats.width} × ${stats.height}` : '—'
  const online = agentOnline !== false

  if (session.isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-24 text-center">
        <MonitorX className="size-8 text-muted-foreground" />
        <p className="font-medium">{errorMessage(session.error)}</p>
        <Button asChild variant="outline" size="sm">
          <Link to="/live">Back to Live Tracking</Link>
        </Button>
      </div>
    )
  }

  return (
    <div ref={stageRef} className="flex h-dvh flex-col overflow-hidden bg-neutral-950 text-white">
      <header className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-white/10 bg-neutral-900/90 px-4 py-3 sm:px-5">
        <Button asChild variant="ghost" size="icon-sm" className="text-white/70 hover:bg-white/10 hover:text-white">
          <Link to="/live" aria-label="Back to Live Tracking">
            <ArrowLeft />
          </Link>
        </Button>
        <div className="flex min-w-0 items-center gap-3">
          <div className="relative">
            <PersonAvatar name={name} seed={employee?.id} className="size-9" />
            <span
              className={cn('absolute right-0 bottom-0 size-2.5 rounded-full ring-2 ring-neutral-900', online ? 'bg-emerald-400' : 'bg-neutral-500')}
              aria-hidden
            />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-[15px] font-semibold">{name}</h1>
            <p className="flex items-center gap-1.5 text-[12px] text-white/60">
              {online ? 'Online' : 'Offline'}
              {session.data?.device && <> · {session.data.device.name}</>}
            </p>
          </div>
          <span
            className={cn('ml-1 inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] font-bold tracking-wider uppercase', badge.className)}
            aria-live="polite"
          >
            {badge.pulse && <span className="size-1.5 animate-pulse rounded-full bg-white motion-reduce:animate-none" aria-hidden />}
            {badge.label}
          </span>
        </div>

        <div className="flex items-center gap-5 sm:ml-auto">
          <Metric label="Quality">
            <QualityMeter stats={stats} live={live} />
          </Metric>
          <Metric label="Resolution">{live ? resolution : '—'}</Metric>
          <Metric label="FPS">{live && stats.fps !== null ? stats.fps : '—'}</Metric>
          <Metric label="Duration">{duration}</Metric>
        </div>

        <div className="flex items-center gap-2">
          {phase === 'ended' ? (
            <Button size="sm" onClick={startAgain} loading={restart.isPending} disabled={!employee}>
              <Play /> Start again
            </Button>
          ) : (
            <Button size="sm" variant="destructive" onClick={stopStream} loading={stopping}>
              <Square className="fill-current" /> Stop stream
            </Button>
          )}
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={toggleFullscreen}
            className="text-white/70 hover:bg-white/10 hover:text-white"
            aria-label={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            title={fullscreen ? 'Exit fullscreen (F)' : 'Fullscreen (F)'}
          >
            {fullscreen ? <Minimize /> : <Maximize />}
          </Button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1 items-center justify-center">
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className={cn('size-full object-contain transition-opacity', live ? 'opacity-100' : 'opacity-40')}
          aria-label={`Live screen of ${name}`}
        />

        {phase !== 'live' && (
          <div className="absolute inset-0 flex items-center justify-center p-6" aria-live="polite">
            {phase === 'ended' ? (
              <div className="max-w-sm rounded-xl border border-white/10 bg-neutral-900/95 p-6 text-center shadow-2xl">
                <MonitorPlay className="mx-auto size-8 text-white/50" aria-hidden />
                <p className="mt-3 font-semibold">Live stream ended</p>
                <p className="mt-1 text-[13px] text-white/60">{endReasonLabel(endReason)}</p>
                {connectedAt && <p className="mt-1 text-[12px] text-white/40 tabular">Watched for {duration}</p>}
                <div className="mt-5 flex justify-center gap-2">
                  <Button asChild size="sm" variant="ghost" className="text-white/80 hover:bg-white/10 hover:text-white">
                    <Link to="/live">Back to Live Tracking</Link>
                  </Button>
                  <Button size="sm" onClick={startAgain} loading={restart.isPending} disabled={!employee}>
                    <Play /> Start again
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 rounded-xl bg-black/60 px-6 py-5 text-center">
                {phase === 'waiting' || networkOffline || (phase === 'reconnecting' && agentOnline === false) ? (
                  <WifiOff className="size-6 text-amber-300" aria-hidden />
                ) : (
                  <Spinner className="size-6 text-white/70" />
                )}
                <p className="text-[14px] font-medium">
                  {networkOffline
                    ? 'Your internet connection is offline'
                    : phase === 'waiting'
                      ? `Waiting for ${first}'s device…`
                      : phase === 'reconnecting'
                        ? agentOnline === false
                          ? `${first}'s computer went offline — waiting for it to return…`
                          : 'Reconnecting…'
                        : `Connecting to ${first}'s screen…`}
                </p>
                <p className="text-[12px] text-white/50">
                  {networkOffline
                    ? 'The stream resumes as soon as you are back online.'
                    : phase === 'reconnecting'
                      ? 'The stream resumes automatically.'
                      : `${first} will be notified when the stream starts.`}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      <footer className="flex items-center gap-2 border-t border-white/10 bg-neutral-900/90 px-4 py-2 text-[11px] text-white/45 sm:px-5">
        <Clock className="size-3" aria-hidden />
        {session.data ? <>Ends automatically at {formatTime(session.data.expires_at)}</> : '…'}
        <span className="ml-auto hidden sm:inline">Peer-to-peer · not recorded · access is audited</span>
      </footer>
    </div>
  )
}

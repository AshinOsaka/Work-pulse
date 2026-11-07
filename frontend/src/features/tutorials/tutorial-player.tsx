import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Maximize, Minimize, Pause, Play, RotateCcw, SkipBack, SkipForward, Volume2, VolumeX } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { audioUrl, type Tutorial } from '@/features/tutorials/data'
import { cn } from '@/lib/utils'

const SCENE_W = 960
const SCENE_H = 540
/** A short pause after each voice-over part before the next step starts. */
const GAP_SECONDS = 0.7
/** Controls fade out after this long without mouse movement while playing. */
const HIDE_CONTROLS_MS = 2500
/** Playback speeds offered, like a video player. The voice keeps its pitch at every speed. */
const SPEEDS = [0.75, 1, 1.25, 1.5]

const clock = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/**
 * Plays a tutorial like a video: the animated scene, its voice-over and captions, with play/pause, a seek bar,
 * previous/next step, sound and full screen. Timing comes from the stored voice-over lengths, so it plays the same
 * with the sound off. Audio is the browser's own player (no service).
 */
export function TutorialPlayer({ tutorial, open, onOpenChange }: { tutorial: Tutorial; open: boolean; onOpenChange: (open: boolean) => void }) {
  const steps = tutorial.captions.length
  const [{ step, t }, setClock] = useState({ step: 0, t: 0 })
  const [playing, setPlaying] = useState(true)
  const [muted, setMuted] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [fullscreen, setFullscreen] = useState(false)
  const [active, setActive] = useState(true)
  // The voice-over player, created on first use (the captions are its text version).
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const playingRef = useRef(playing)
  const speedRef = useRef(speed)
  // Where in the next step's voice-over to start after a seek.
  const offsetRef = useRef(0)
  const hideTimer = useRef<number | undefined>(undefined)
  const stage = useRef<HTMLDivElement>(null)

  const lengthOf = useCallback((s: number) => (tutorial.durations[s] ?? 5) + GAP_SECONDS, [tutorial.durations])
  const starts = useMemo(() => {
    const list: number[] = []
    let sum = 0
    for (let i = 0; i < steps; i++) {
      list.push(sum)
      sum += lengthOf(i)
    }
    return { list, total: sum }
  }, [steps, lengthOf])
  const stepLength = lengthOf(step)
  const finished = step === steps - 1 && t >= stepLength
  const now = Math.min(starts.total, (starts.list[step] ?? 0) + t)

  // The clock: advances t while playing; moves to the next step when this one's voice-over is done.
  useEffect(() => {
    if (!open || !playing || finished) return
    let last = performance.now()
    let frame = 0
    const tick = (stamp: number) => {
      const dt = ((stamp - last) / 1000) * speed
      last = stamp
      setClock((c) => {
        const next = c.t + dt
        if (next >= lengthOf(c.step) && c.step < steps - 1) return { step: c.step + 1, t: 0 }
        return { ...c, t: next }
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [open, playing, finished, lengthOf, steps, speed])

  // Voice-over: load (and start, when playing) the step's part whenever the step changes.
  useEffect(() => {
    if (!open) return
    audioRef.current ??= new Audio()
    const audio = audioRef.current
    audio.src = audioUrl(tutorial.slug, step)
    audio.playbackRate = speedRef.current
    const offset = offsetRef.current
    offsetRef.current = 0
    if (offset > 0) audio.addEventListener('loadedmetadata', () => (audio.currentTime = offset), { once: true })
    if (playingRef.current) void audio.play().catch(() => undefined)
  }, [open, step, tutorial.slug])

  // Follow play/pause and mute.
  useEffect(() => {
    playingRef.current = playing
    const audio = audioRef.current
    if (!audio) return
    audio.muted = muted
    speedRef.current = speed
    audio.playbackRate = speed
    if (open && playing && !finished) void audio.play().catch(() => undefined)
    else audio.pause()
  }, [open, playing, muted, finished, speed])

  // Stop the sound and timers when the player closes.
  useEffect(
    () => () => {
      audioRef.current?.pause()
      window.clearTimeout(hideTimer.current)
    },
    [],
  )

  // Controls start visible and fade like after any mouse movement (they come back on the next one).
  useEffect(() => {
    hideTimer.current = window.setTimeout(() => setActive(false), HIDE_CONTROLS_MS)
  }, [])

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stage.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  /** Jump to a moment of the whole tutorial (seconds from the start). */
  const seek = (seconds: number) => {
    const g = Math.max(0, Math.min(starts.total - 0.05, seconds))
    let s = 0
    while (s < steps - 1 && g >= starts.list[s + 1]) s++
    const local = g - starts.list[s]
    const voice = tutorial.durations[s] ?? 0
    if (s === step && audioRef.current) {
      // Same step: move the voice-over directly (the step effect won't run).
      const audio = audioRef.current
      if (local < voice) {
        audio.currentTime = local
        if (playingRef.current) void audio.play().catch(() => undefined)
      } else audio.pause()
    } else {
      offsetRef.current = local < voice ? local : voice
    }
    setClock({ step: s, t: local })
  }

  const restartAt = (s: number) => {
    playingRef.current = true
    setPlaying(true)
    seek(starts.list[Math.max(0, Math.min(steps - 1, s))])
  }

  const togglePlay = () => (finished ? restartAt(0) : setPlaying((p) => !p))

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void stage.current?.requestFullscreen().catch(() => undefined)
  }

  const wake = () => {
    setActive(true)
    window.clearTimeout(hideTimer.current)
    hideTimer.current = window.setTimeout(() => setActive(false), HIDE_CONTROLS_MS)
  }

  // Keyboard: Space/K play-pause, ← → five seconds, F full screen, M sound.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, select')) return
      const key = e.key.toLowerCase()
      if (key === ' ' || key === 'k') {
        if (target?.closest('button')) return // the focused button handles its own Space
        e.preventDefault()
        document.getElementById('tutorial-play')?.click()
      } else if (key === 'arrowright' || key === 'arrowleft') {
        e.preventDefault()
        document.getElementById(key === 'arrowright' ? 'tutorial-forward5' : 'tutorial-back5')?.click()
      } else if (key === 'f') document.getElementById('tutorial-fullscreen')?.click()
      else if (key === 'm') document.getElementById('tutorial-mute')?.click()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const showControls = active || !playing || finished
  const caption = tutorial.captions[step]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="px-5 pt-4 pb-3">
          <DialogTitle className="flex items-center gap-2">
            <Play className="size-3.5 fill-primary text-primary" aria-hidden /> {tutorial.title}
          </DialogTitle>
          <DialogDescription className="sr-only">{tutorial.description}</DialogDescription>
        </DialogHeader>

        <div
          ref={stage}
          onPointerMove={wake}
          onPointerDown={wake}
          className={cn('relative overflow-hidden border-t bg-black', fullscreen ? 'flex items-center' : '', !showControls && 'cursor-none')}
        >
          <ScaledScene fullscreen={fullscreen}>
            <tutorial.scene step={step} t={t} />
          </ScaledScene>

          {/* Click the picture to play / pause, like a video. */}
          <button type="button" className="absolute inset-0 bottom-16 cursor-[inherit]" onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'} tabIndex={-1} />

          {fullscreen && (
            <p className="pointer-events-none absolute inset-x-0 bottom-20 mx-auto w-fit max-w-[80%] rounded-lg bg-black/70 px-4 py-2 text-center text-[16px] text-white" aria-live="polite">
              {caption}
            </p>
          )}

          {/* Video controls */}
          <div
            className={cn(
              'absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/45 to-transparent px-4 pt-10 pb-2.5 text-white transition-opacity duration-300',
              showControls ? 'opacity-100' : 'pointer-events-none opacity-0',
            )}
          >
            <SeekBar now={now} total={starts.total} marks={starts.list} onSeek={seek} />
            <div className="mt-1.5 flex items-center gap-1">
              <ControlButton id="tutorial-play" label={finished ? 'Replay' : playing ? 'Pause' : 'Play'} onClick={togglePlay}>
                {finished ? <RotateCcw className="size-5" /> : playing ? <Pause className="size-5 fill-white" /> : <Play className="size-5 fill-white" />}
              </ControlButton>
              <ControlButton label="Previous step" onClick={() => restartAt(t > 1.5 ? step : step - 1)}>
                <SkipBack className="size-4 fill-white" />
              </ControlButton>
              <ControlButton label="Next step" onClick={() => restartAt(step + 1)} disabled={step >= steps - 1}>
                <SkipForward className="size-4 fill-white" />
              </ControlButton>
              <span className="ml-1.5 text-[13px] font-medium tabular">
                {clock(now)} / {clock(starts.total)}
              </span>
              <span className="ml-3 hidden truncate text-[12px] text-white/70 sm:inline">
                Step {step + 1} of {steps}
              </span>
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => setSpeed((v) => SPEEDS[(SPEEDS.indexOf(v) + 1) % SPEEDS.length])}
                title="Playback speed"
                aria-label={`Playback speed ${speed}×, click to change`}
                className="h-8 min-w-12 rounded-full px-2.5 text-[13px] font-semibold tabular transition hover:bg-white/15 focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:outline-none"
              >
                {speed}×
              </button>
              <ControlButton id="tutorial-mute" label={muted ? 'Sound on' : 'Sound off'} onClick={() => setMuted((m) => !m)}>
                {muted ? <VolumeX className="size-5" /> : <Volume2 className="size-5" />}
              </ControlButton>
              <ControlButton id="tutorial-fullscreen" label={fullscreen ? 'Exit full screen' : 'Full screen'} onClick={toggleFullscreen}>
                {fullscreen ? <Minimize className="size-5" /> : <Maximize className="size-5" />}
              </ControlButton>
              {/* Hidden targets for the ← → keys. */}
              <button id="tutorial-back5" type="button" className="hidden" tabIndex={-1} aria-hidden onClick={() => seek(now - 5)} />
              <button id="tutorial-forward5" type="button" className="hidden" tabIndex={-1} aria-hidden onClick={() => seek(now + 5)} />
            </div>
          </div>
        </div>

        {/* Caption */}
        {!fullscreen && (
          <p className="min-h-[3.25rem] border-t bg-subtle/60 px-5 py-3 text-center text-[13px] leading-snug" aria-live="polite">
            {caption}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ControlButton({ id, label, onClick, disabled, children }: { id?: string; label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      id={id}
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="flex size-9 items-center justify-center rounded-full transition hover:bg-white/15 focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:outline-none disabled:opacity-40"
    >
      {children}
    </button>
  )
}

/** The video-style progress bar: a native range input (drag, click and arrow keys) drawn as a thin track; faint
 *  ticks mark where each step starts. */
function SeekBar({ now, total, marks, onSeek }: { now: number; total: number; marks: number[]; onSeek: (seconds: number) => void }) {
  const pct = total ? (100 * now) / total : 0
  return (
    <div className="group/seek relative flex h-4 items-center">
      <div className="relative h-1 w-full rounded-full bg-white/30 transition-[height] group-hover/seek:h-1.5">
        <div className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${pct}%` }} />
        {marks.slice(1).map((m) => (
          <span key={m} className="absolute inset-y-0 w-0.5 bg-black/40" style={{ left: `${(100 * m) / total}%` }} />
        ))}
      </div>
      <span
        className="pointer-events-none absolute size-3.5 -translate-x-1/2 scale-0 rounded-full bg-white shadow transition-transform group-hover/seek:scale-100 group-has-[:focus-visible]/seek:scale-100"
        style={{ left: `${pct}%` }}
      />
      <input
        type="range"
        min={0}
        max={total}
        step={0.1}
        value={now}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Seek"
        aria-valuetext={`${clock(now)} of ${clock(total)}`}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
      />
    </div>
  )
}

/** Fits the fixed 960 × 540 scene to the space: the dialog's width, or the whole screen in full screen. */
function ScaledScene({ fullscreen, children }: { fullscreen: boolean; children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: SCENE_W, h: SCENE_H })
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const scale = Math.min(size.w / SCENE_W, size.h / SCENE_H)
  return (
    <div ref={box} className={cn('relative w-full overflow-hidden', fullscreen ? 'h-screen' : 'aspect-video')} aria-hidden>
      <div
        className="absolute top-0 left-0 origin-top-left"
        style={{
          width: SCENE_W,
          height: SCENE_H,
          transform: `translate(${(size.w - SCENE_W * scale) / 2}px, ${(size.h - SCENE_H * scale) / 2}px) scale(${scale})`,
        }}
      >
        {children}
      </div>
    </div>
  )
}

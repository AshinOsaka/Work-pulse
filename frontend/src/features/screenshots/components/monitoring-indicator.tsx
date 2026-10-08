import { AppWindow, Camera, Clock, Eye, MonitorPlay } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useMyMonitoring } from '@/features/screenshots/api'
import { scheduleSummary } from '@/features/screenshots/format'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

function Line({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0">
        <p className="text-[12px] text-muted-foreground">{label}</p>
        <p className="text-[13px] font-medium">{value}</p>
      </div>
    </div>
  )
}

/**
 * Tells the signed-in person, at all times, whether they are being monitored right now and how.
 * Hidden for accounts without an employee record (e.g. a platform operator).
 */
export function MonitoringIndicator() {
  const hasEmployee = useAuthStore((s) => Boolean(s.user?.employee_id))
  const { data } = useMyMonitoring(hasEmployee)
  if (!data?.has_employee_record) return null
  const shots = data.screenshots
  const active = data.monitoring_active
  const screenshotsNow = active && shots?.enabled && shots.in_schedule_now
  const label = data.live_viewer
    ? `Live view: ${data.live_viewer}`
    : active
      ? screenshotsNow
        ? 'Screenshots active'
        : 'Activity recorded'
      : 'Not monitored now'

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn(
            'h-8 gap-1.5 rounded-full px-2.5 text-[12px]',
            active ? 'bg-destructive-soft text-destructive hover:bg-destructive-soft/80 hover:text-destructive' : 'text-muted-foreground',
          )}
          aria-label={`Monitoring status: ${label}`}
        >
          <span className="relative flex size-2" aria-hidden>
            {active && <span className="absolute inline-flex size-full animate-ping rounded-full bg-destructive opacity-60 motion-reduce:hidden" />}
            <span className={cn('relative inline-flex size-2 rounded-full', active ? 'bg-destructive' : 'bg-muted-foreground/50')} />
          </span>
          <span className="hidden md:inline">{label}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3">
        <div>
          <p className="flex items-center gap-1.5 text-[13px] font-semibold">
            <Eye className="size-4 text-muted-foreground" aria-hidden /> What WorkPulse records about you
          </p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {data.session_active
              ? 'Your work session is running on the desktop agent.'
              : data.agent_connected
                ? 'The desktop agent is connected, but no work session is running: nothing is recorded.'
                : 'The desktop agent is not connected: nothing is recorded.'}
          </p>
        </div>
        <div className="space-y-2.5 border-t pt-3">
          <Line
            icon={AppWindow}
            label="Applications"
            value={
              data.track_applications
                ? data.capture_window_titles
                  ? 'Application names and window titles'
                  : 'Application names (no window titles)'
                : 'Not recorded'
            }
          />
          <Line
            icon={Camera}
            label="Screenshots"
            value={
              shots?.enabled
                ? `${scheduleSummary(shots)}${shots.in_schedule_now ? '' : ' (outside hours now)'}`
                : 'Off'
            }
          />
          <Line
            icon={MonitorPlay}
            label="Live screen viewing"
            value={
              data.live_viewer
                ? `${data.live_viewer} is viewing your screen now`
                : data.live_view_enabled
                  ? 'Allowed during work sessions; you are notified'
                  : 'Off'
            }
          />
          {shots?.enabled && (
            <Line
              icon={Clock}
              label="Last screenshot · kept for"
              value={`${shots.last_captured_at ? formatRelative(shots.last_captured_at) : 'None yet'} · ${shots.retention_days} days`}
            />
          )}
        </div>
        <p className="border-t pt-3 text-[12px] text-muted-foreground">
          Never recorded: keystrokes or typed text, passwords, clipboard, or the window titles of password managers, private
          windows, messaging and e-mail.{' '}
          <Link to="/privacy" className="font-medium text-primary hover:underline">
            Full monitoring policy
          </Link>
        </p>
      </PopoverContent>
    </Popover>
  )
}

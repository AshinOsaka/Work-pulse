import type { LiveAvailability } from '@/types/api'

export const END_REASONS: Record<string, string> = {
  viewer_stopped: 'You stopped the stream.',
  viewer_disconnected: 'The viewer lost its connection and did not return in time.',
  agent_disconnected: "The employee's computer went offline.",
  connection_lost: 'The connection was lost and could not be restored.',
  connect_timeout: "The employee's computer did not respond in time.",
  max_duration: 'The stream reached the maximum length set by your workspace.',
  work_session_stopped: 'The employee ended their work session.',
  not_working: 'The employee is not in a work session.',
  live_view_disabled: 'Live viewing was turned off for the workspace.',
  signed_out: 'The desktop agent signed out.',
  agent_stopped: 'The desktop agent was closed.',
  agent_error: 'The desktop agent could not stream the screen.',
  capture_failed: "The employee's screen could not be captured.",
  server_shutdown: 'The WorkPulse server restarted.',
  server_restart: 'The WorkPulse server restarted.',
  not_available: 'This stream is no longer available.',
  forbidden: 'You are not allowed to view this stream.',
}

/** Neutral wording for the session log, read by people other than the viewer. */
export const LOG_REASONS: Record<string, string> = {
  viewer_stopped: 'Stopped by viewer',
  viewer_disconnected: 'Viewer disconnected',
  agent_disconnected: 'Employee went offline',
  connection_lost: 'Connection lost',
  connect_timeout: 'Never connected (timeout)',
  max_duration: 'Reached time limit',
  work_session_stopped: 'Work session ended',
  not_working: 'Not in a work session',
  live_view_disabled: 'Live viewing turned off',
  signed_out: 'Agent signed out',
  agent_stopped: 'Agent closed',
  agent_error: 'Agent error',
  capture_failed: 'Screen capture failed',
  server_shutdown: 'Server restarted',
  server_restart: 'Server restarted',
}

export function endReasonLabel(reason: string | null): string {
  return (reason && END_REASONS[reason]) || 'The stream has ended.'
}

export const AVAILABILITY: Record<LiveAvailability, { label: string; hint: string }> = {
  available: { label: 'Working', hint: 'Ready for live view' },
  in_session: { label: 'Live now', hint: 'Being viewed' },
  not_working: { label: 'Online', hint: 'Not in a work session' },
  offline: { label: 'Offline', hint: 'Desktop agent not connected' },
  disabled: { label: 'Unavailable', hint: 'Live viewing is off' },
}

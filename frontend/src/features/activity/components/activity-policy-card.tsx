import { useState, type FormEvent, type ReactNode } from 'react'
import { ShieldCheck, X } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { useActivityPolicy, useUpdateActivityPolicy } from '@/features/activity/api'
import { errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { ActivityPolicy } from '@/types/api'

const NEVER_RECORDED = ['Keystrokes or typed text', 'Passwords', 'Clipboard contents', 'Message or e-mail contents']

function SettingRow({ id, title, description, children }: { id: string; title: string; description: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 py-3">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{title}</Label>
        <p className="text-[12px] text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  )
}

function PolicyForm({ policy, editable }: { policy: ActivityPolicy; editable: boolean }) {
  const update = useUpdateActivityPolicy()
  const [form, setForm] = useState(policy)
  const [draft, setDraft] = useState('')
  const dirty =
    form.track_applications !== policy.track_applications ||
    form.capture_window_titles !== policy.capture_window_titles ||
    form.track_websites !== policy.track_websites ||
    form.excluded_apps.join('\n') !== policy.excluded_apps.join('\n')

  const addExclusion = () => {
    const name = draft.trim()
    if (name && !form.excluded_apps.some((a) => a.toLowerCase() === name.toLowerCase())) {
      setForm({ ...form, excluded_apps: [...form.excluded_apps, name].sort((a, b) => a.localeCompare(b)) })
    }
    setDraft('')
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    update.mutate(form, {
      onSuccess: (saved) => {
        setForm(saved)
        toast.success('Activity policy updated', { description: 'Desktop agents pick up the change within a minute.' })
      },
    })
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <CardContent className="space-y-4">
        {update.error && <FormAlert>{errorMessage(update.error)}</FormAlert>}
        <div className="divide-y">
          <SettingRow
            id="track-applications"
            title="Track application usage"
            description="Record which application is in the foreground during work sessions, and for how long."
          >
            <Switch
              id="track-applications"
              checked={form.track_applications}
              onCheckedChange={(v) =>
                setForm({ ...form, track_applications: v, capture_window_titles: v && form.capture_window_titles, track_websites: v && form.track_websites })
              }
              disabled={!editable}
            />
          </SettingRow>
          <SettingRow
            id="track-websites"
            title="Record websites (domain only)"
            description="For browser time, records the site's domain (e.g. github.com) so website rules can apply. Never the full address, page title, or anything typed, and never in private/incognito windows. Exclusions also apply to domains."
          >
            <Switch
              id="track-websites"
              checked={form.track_websites}
              onCheckedChange={(v) => setForm({ ...form, track_websites: v })}
              disabled={!editable || !form.track_applications}
            />
          </SettingRow>
          <SettingRow
            id="capture-titles"
            title="Record window titles"
            description="Adds the window title, e.g. a document name. Never recorded for password managers, private browsing, messaging or e-mail; links, e-mail addresses and long numbers are removed."
          >
            <Switch
              id="capture-titles"
              checked={form.capture_window_titles}
              onCheckedChange={(v) => setForm({ ...form, capture_window_titles: v })}
              disabled={!editable || !form.track_applications}
            />
          </SettingRow>
        </div>

        <div className="space-y-2">
          <Label htmlFor="excluded-app">Excluded applications</Label>
          <p className="text-[12px] text-muted-foreground">
            Never tracked: matched by application name (e.g. “Spotify”) or executable (e.g. “spotify.exe”).
          </p>
          {editable && (
            <div className="flex gap-2">
              <Input
                id="excluded-app"
                value={draft}
                maxLength={120}
                placeholder="Application name or executable"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addExclusion()
                  }
                }}
              />
              <Button type="button" variant="outline" onClick={addExclusion} disabled={!draft.trim()}>
                Add
              </Button>
            </div>
          )}
          {form.excluded_apps.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">No applications are excluded.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5" aria-label="Excluded applications">
              {form.excluded_apps.map((app) => (
                <li key={app}>
                  <Badge variant="secondary" className="gap-1 py-1 pr-1 text-[12px]">
                    {app}
                    {editable && (
                      <button
                        type="button"
                        className="rounded p-0.5 hover:bg-background"
                        aria-label={`Remove ${app}`}
                        onClick={() => setForm({ ...form, excluded_apps: form.excluded_apps.filter((a) => a !== app) })}
                      >
                        <X className="size-3" />
                      </button>
                    )}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border bg-subtle px-4 py-3">
          <p className="flex items-center gap-1.5 text-[13px] font-medium">
            <ShieldCheck className="size-4 text-success" aria-hidden /> Never recorded, whatever the policy
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">{NEVER_RECORDED.join(' · ')}</p>
        </div>
      </CardContent>
      {editable && (
        <CardFooter className="justify-end">
          <Button type="submit" size="sm" disabled={!dirty} loading={update.isPending}>
            Save policy
          </Button>
        </CardFooter>
      )}
    </form>
  )
}

/** Workspace activity tracking policy. Everyone can read it (transparency); admins can change it. */
export function ActivityPolicyCard() {
  const { can } = usePermissions()
  const query = useActivityPolicy()
  const editable = can('POLICY_MANAGE')
  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity tracking</CardTitle>
        <CardDescription>
          {editable
            ? 'What the desktop agent records while employees are in a work session.'
            : 'What the desktop agent records while you are in a work session. Only administrators can change this.'}
        </CardDescription>
      </CardHeader>
      {query.isError ? (
        <CardContent>
          <FormAlert>{errorMessage(query.error)}</FormAlert>
        </CardContent>
      ) : !query.data ? (
        <CardContent className="space-y-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </CardContent>
      ) : (
        <PolicyForm key={JSON.stringify(query.data)} policy={query.data} editable={editable} />
      )}
    </Card>
  )
}

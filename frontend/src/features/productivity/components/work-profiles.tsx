import { useState, type FormEvent } from 'react'
import { BriefcaseBusiness, Plus, Trash2, Users } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FormAlert, FormField } from '@/components/common/form-field'
import { AvatarGroup } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { useEmployeeOptions } from '@/features/people/api'
import { useCreateProfile, useDeleteProfile, useProfileTemplates, useSetProfileMembers, useWorkProfiles } from '@/features/productivity/api'
import { CATEGORY } from '@/features/productivity/meta'
import { AssigneePicker } from '@/features/work/components/assignee-picker'
import { ApiError, errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { EmployeeRef, WorkProfile } from '@/types/api'

const BLANK = '__blank__'

function NewProfileDialog({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const templates = useProfileTemplates()
  const create = useCreateProfile()
  const [template, setTemplate] = useState<string>(BLANK)
  const [name, setName] = useState('')
  const chosen = templates.data?.find((t) => t.key === template)
  const errors = create.error instanceof ApiError ? create.error.fieldErrors : {}

  const pick = (key: string) => {
    setTemplate(key)
    const t = templates.data?.find((x) => x.key === key)
    if (t && (!name || templates.data?.some((x) => x.name === name))) setName(t.name)
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(
      { name: name.trim(), template: template === BLANK ? null : template },
      {
        onSuccess: (p) => {
          toast.success(`${p.name} created${p.rule_count ? ` with ${p.rule_count} rules` : ''}`)
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>New work profile</DialogTitle>
            <DialogDescription>
              A job role with its own activity context. Its rules apply to its members on top of the company, department and team rules.
            </DialogDescription>
          </DialogHeader>
          {create.error && !Object.keys(errors).length && <FormAlert>{errorMessage(create.error)}</FormAlert>}
          <fieldset className="space-y-2">
            <legend className="mb-1.5 text-[13px] font-medium">Start from</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {[{ key: BLANK, name: 'Blank', description: 'No rules yet; add your own.' }, ...(templates.data ?? [])].map((t) => (
                <button
                  key={t.key}
                  type="button"
                  aria-pressed={template === t.key}
                  onClick={() => pick(t.key)}
                  className={cn(
                    'rounded-lg border p-3 text-left transition hover:border-primary/50',
                    template === t.key && 'border-primary bg-primary-soft/40 ring-1 ring-primary',
                  )}
                >
                  <span className="block text-[13px] font-medium">{t.name}</span>
                  <span className="block text-[11px] text-muted-foreground">{t.description}</span>
                </button>
              ))}
              {!templates.data && <Skeleton className="h-16 sm:col-span-2" />}
            </div>
          </fieldset>
          {chosen && (
            <div className="space-y-1.5">
              <Label>Rules it starts with ({chosen.rules.length})</Label>
              <ul className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto rounded-lg border bg-subtle p-2">
                {chosen.rules.map((r) => (
                  <li key={`${r.kind}:${r.pattern}`} className="inline-flex items-center gap-1 rounded bg-card px-1.5 py-0.5 text-[11px]">
                    <span className={cn('size-2 rounded-sm', CATEGORY[r.category].swatch)} aria-hidden />
                    {r.pattern}
                    <span className="sr-only">: {CATEGORY[r.category].label}</span>
                  </li>
                ))}
              </ul>
              <p className="text-[11px] text-muted-foreground">Colour = category (productive, neutral, unproductive). You can change any of them afterwards.</p>
            </div>
          )}
          <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} maxLength={60} required />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={name.trim().length < 2}>
              Create profile
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function MembersDialog({ profile, onOpenChange }: { profile: WorkProfile; onOpenChange: (open: boolean) => void }) {
  const people = useEmployeeOptions()
  const save = useSetProfileMembers()
  const [ids, setIds] = useState(profile.members.map((m) => m.id))
  const everyone: EmployeeRef[] = (people.data ?? []).map((p) => ({ id: p.id, full_name: p.full_name, email: '', job_title: p.job_title ?? null, status: 'active' }))
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Members of {profile.name}</DialogTitle>
          <DialogDescription>Each person has at most one work profile; adding someone here moves them from any other profile.</DialogDescription>
        </DialogHeader>
        <AssigneePicker members={everyone} value={ids} onChange={setIds} label={`${profile.name} members`} placeholder="Add people" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { id: profile.id, employee_ids: ids },
                {
                  onSuccess: () => {
                    toast.success('Members updated')
                    onOpenChange(false)
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Job roles (Developer, Designer, Accountant, Sales, Support…): each with its own activity context. */
export function WorkProfilesCard({ editable }: { editable: boolean }) {
  const profiles = useWorkProfiles()
  const remove = useDeleteProfile()
  const [creating, setCreating] = useState(false)
  const [members, setMembers] = useState<WorkProfile | null>(null)
  const [deleting, setDeleting] = useState<WorkProfile | null>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BriefcaseBusiness className="size-4 text-muted-foreground" aria-hidden /> Work profiles
        </CardTitle>
        <CardDescription>
          The same application can mean different things in different jobs — LinkedIn is prospecting in Sales, Figma is the work for Designers. A
          profile&apos;s rules are the most specific: they override team, department, role and company rules for its members.
        </CardDescription>
        {editable && (
          <CardAction>
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus /> New profile
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <div className="mt-3 border-t">
        {!profiles.data ? (
          <div className="p-5">
            <Skeleton className="h-20" />
          </div>
        ) : profiles.data.length === 0 ? (
          <EmptyState
            size="sm"
            icon={BriefcaseBusiness}
            title="No work profiles yet"
            description={editable ? 'Start from a Developer, Designer, Accountant, Sales or Support template, then assign people.' : 'An administrator can add them.'}
          />
        ) : (
          <ul className="divide-y">
            {profiles.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium">{p.name}</p>
                  <p className="text-[12px] text-muted-foreground">
                    {p.rule_count} rule{p.rule_count === 1 ? '' : 's'} · {p.members.length} {p.members.length === 1 ? 'person' : 'people'}
                    {p.description && ` · ${p.description}`}
                  </p>
                </div>
                <AvatarGroup people={p.members} max={6} />
                {editable && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => setMembers(p)}>
                      <Users /> Members
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => setDeleting(p)}>
                      <Trash2 />
                    </Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {creating && <NewProfileDialog onOpenChange={setCreating} />}
      {members && <MembersDialog key={members.id} profile={members} onOpenChange={(open) => !open && setMembers(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? ''}?`}
        description="Its rules are removed and its members fall back to the company, department and team rules. All productivity figures are recalculated."
        confirmLabel="Delete profile"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: (e) => toast.error(errorMessage(e)) })}
      />
    </Card>
  )
}
